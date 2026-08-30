"""Web Push: chave VAPID, inscrição do aparelho, teste e disparo diário de lembretes (cron)."""
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import select

from app.erros import ErroApi
from app.extensoes import db
from app.modelos import InscricaoPush
from app.rotas.auth import usuario_atual
from app.servicos import notificacoes as svc

bp = Blueprint("notificacoes", __name__, url_prefix="/notificacoes")


@bp.get("/vapid")
def vapid():
    """Chave pública para o navegador assinar o push. Sem autenticação (não é segredo)."""
    return jsonify({"chave_publica": current_app.config.get("VAPID_PUBLIC_KEY", ""), "ativo": svc.configurado()})


@bp.get("/inscricoes")
@jwt_required()
def listar():
    u = usuario_atual()
    itens = db.session.execute(select(InscricaoPush).where(InscricaoPush.usuario_id == u.id)).scalars().all()
    return jsonify({"dados": [i.para_dict() for i in itens], "ativo": svc.configurado()})


@bp.post("/inscrever")
@jwt_required()
def inscrever():
    u = usuario_atual()
    corpo = request.get_json(silent=True) or {}
    endpoint = (corpo.get("endpoint") or "").strip()
    chaves = corpo.get("keys") or {}
    if not endpoint or not chaves.get("p256dh") or not chaves.get("auth"):
        raise ErroApi("VALIDACAO", "Assinatura de push incompleta (endpoint, keys.p256dh, keys.auth).", 422)
    insc = db.session.execute(select(InscricaoPush).where(InscricaoPush.endpoint == endpoint)).scalar_one_or_none()
    if insc is None:
        insc = InscricaoPush(endpoint=endpoint)
        db.session.add(insc)
    insc.usuario_id = u.id
    insc.p256dh = chaves["p256dh"]
    insc.auth = chaves["auth"]
    insc.aparelho = (corpo.get("aparelho") or request.user_agent.string or "")[:200]
    db.session.commit()
    return jsonify(insc.para_dict()), 201


@bp.delete("/inscrever")
@jwt_required()
def desinscrever():
    u = usuario_atual()
    corpo = request.get_json(silent=True) or {}
    endpoint = (corpo.get("endpoint") or "").strip()
    q = select(InscricaoPush).where(InscricaoPush.usuario_id == u.id)
    if endpoint:
        q = q.where(InscricaoPush.endpoint == endpoint)
    for i in db.session.execute(q).scalars().all():
        db.session.delete(i)
    db.session.commit()
    return "", 204


@bp.post("/testar")
@jwt_required()
def testar():
    if not svc.configurado():
        raise ErroApi("PUSH_INATIVO", "Notificações não configuradas no servidor.", 503)
    u = usuario_atual()
    n = svc.enviar_para_usuario(u.id, "Finan está funcionando 🎉", "Você vai receber lembretes de contas por aqui.", "/contas", "teste")
    return jsonify({"enviados": n})


@bp.post("/enviar-lembretes")
def enviar_lembretes():
    """Chamado pelo cron da VPS uma vez por dia. Protegido por X-Cron-Token."""
    token = current_app.config.get("CRON_TOKEN", "")
    if not token or request.headers.get("X-Cron-Token", "") != token:
        raise ErroApi("NAO_AUTORIZADO", "Token do cron inválido.", 401)
    if not svc.configurado():
        return jsonify({"ativo": False, "usuarios": 0, "enviados": 0})
    resumo = svc.lembretes_de_vencimento()
    return jsonify({"ativo": True, **resumo})
