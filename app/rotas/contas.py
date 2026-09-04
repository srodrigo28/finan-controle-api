"""Contas agendadas/recorrentes e suas ocorrências mensais."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import select

from app.erros import ErroApi
from app.esquemas.conta import AtualizarConta, AtualizarOcorrencia, CriarConta, PagarOcorrencia
from app.extensoes import db
from app.modelos import ContaAgendada, OcorrenciaConta
from app.servicos.categorias import categoria_do_usuario
from app.servicos.contas import (
    buscar_conta,
    buscar_ocorrencia,
    excluir_conta,
    gerar_ocorrencias,
    realinhar_ocorrencias,
    resumo_conta,
    pagar_ocorrencia,
    reabrir_ocorrencia,
)
from app.servicos.tempo import hoje, parse_mes
from app.util import parse_uuid, usuario_id, validar

bp = Blueprint("contas", __name__, url_prefix="/contas")


@bp.get("")
@jwt_required()
def listar():
    consulta = select(ContaAgendada).where(ContaAgendada.usuario_id == usuario_id())
    if request.args.get("incluir_inativas", "0") != "1":
        consulta = consulta.where(ContaAgendada.ativa.is_(True))
    contas = db.session.scalars(consulta.order_by(ContaAgendada.dia_vencimento, ContaAgendada.nome)).all()
    return jsonify({"dados": [c.para_dict() for c in contas]})


@bp.post("")
@jwt_required()
def criar():
    uid = usuario_id()
    dados = validar(CriarConta)
    categoria_do_usuario(uid, dados.categoria_id)
    if dados.id is not None and db.session.get(ContaAgendada, dados.id) is not None:
        raise ErroApi("CONFLITO", "Já existe conta com este id.", 409)
    conta = ContaAgendada(usuario_id=uid, **dados.model_dump(exclude_none=True))
    db.session.add(conta)
    db.session.commit()
    return jsonify(conta.para_dict()), 201


@bp.get("/<cid>")
@jwt_required()
def detalhar(cid: str):
    conta = buscar_conta(usuario_id(), parse_uuid(cid))
    return jsonify({**conta.para_dict(), "resumo": resumo_conta(conta)})


@bp.get("/<cid>/ocorrencias")
@jwt_required()
def historico(cid: str):
    """Últimas ocorrências da conta (mais recentes primeiro) — o histórico da tela de detalhe."""
    conta = buscar_conta(usuario_id(), parse_uuid(cid))
    limite = max(1, min(request.args.get("limite", 12, type=int) or 12, 60))
    h = hoje()
    lista = db.session.scalars(
        select(OcorrenciaConta)
        .where(OcorrenciaConta.conta_id == conta.id)
        .order_by(OcorrenciaConta.vencimento.desc())
        .limit(limite)
    ).all()
    return jsonify({"dados": [o.para_dict(h) for o in lista]})


@bp.patch("/<cid>")
@jwt_required()
def atualizar(cid: str):
    conta = buscar_conta(usuario_id(), parse_uuid(cid))
    dados = validar(AtualizarConta)
    campos = dados.campos_enviados()
    if "categoria_id" in campos:
        categoria_do_usuario(conta.usuario_id, campos["categoria_id"])
    muda_calendario = any(
        campo in campos and campos[campo] != getattr(conta, campo)
        for campo in ("dia_vencimento", "recorrencia", "mes_referencia", "ano_referencia")
    )
    for campo, valor in campos.items():
        setattr(conta, campo, valor)
    if muda_calendario:
        realinhar_ocorrencias(conta)
    db.session.commit()
    return jsonify(conta.para_dict())


@bp.delete("/<cid>")
@jwt_required()
def remover(cid: str):
    """Sem parâmetro, arquiva (reversível). Com `?definitivo=1`, apaga de vez."""
    conta = buscar_conta(usuario_id(), parse_uuid(cid))
    if request.args.get("definitivo") == "1":
        excluir_conta(conta)
    else:
        conta.ativa = False
    db.session.commit()
    return "", 204


@bp.get("/ocorrencias")
@jwt_required()
def ocorrencias():
    uid = usuario_id()
    ano, mes = parse_mes(request.args.get("competencia"))
    lista = gerar_ocorrencias(uid, ano, mes)
    db.session.commit()
    h = hoje()
    dados = [o.para_dict(h) for o in lista]
    total_pago = sum((o.valor_real or 0) for o in lista if o.status == "paga")
    # Pulada é "esse mês não tem": não entra no que ainda falta pagar.
    total_pendente = sum(
        (o.valor_real if o.valor_real is not None else (o.conta.valor_estimado or 0))
        for o in lista
        if o.status not in ("paga", "pulada")
    )
    return jsonify({
        "dados": dados,
        "competencia": f"{ano:04d}-{mes:02d}",
        "total_pendente": float(total_pendente),
        "total_pago": float(total_pago),
    })


@bp.post("/ocorrencias/<oid>/pagar")
@jwt_required()
def pagar(oid: str):
    uid = usuario_id()
    oc = buscar_ocorrencia(uid, parse_uuid(oid))
    dados = validar(PagarOcorrencia)
    lanc = pagar_ocorrencia(uid, oc, dados.valor_real, dados.data, dados.forma_pagamento)
    db.session.commit()
    return jsonify({"ocorrencia": oc.para_dict(), "lancamento": lanc.para_dict()})


@bp.patch("/ocorrencias/<oid>")
@jwt_required()
def ajustar_ocorrencia(oid: str):
    """Ajusta só este mês: valor, vencimento ou pular. Ocorrência paga precisa ser reaberta antes."""
    oc = buscar_ocorrencia(usuario_id(), parse_uuid(oid))
    if oc.status == "paga":
        raise ErroApi("CONFLITO", "Ocorrência paga: reabra antes de ajustar.", 409)
    campos = validar(AtualizarOcorrencia).campos_enviados()
    for campo, valor in campos.items():
        setattr(oc, campo, valor)
    db.session.commit()
    return jsonify(oc.para_dict(hoje()))


@bp.delete("/ocorrencias/<oid>")
@jwt_required()
def excluir_ocorrencia(oid: str):
    """Remove a ocorrência deste mês. Ela volta a ser gerada se a conta ainda vencer na competência."""
    oc = buscar_ocorrencia(usuario_id(), parse_uuid(oid))
    if oc.status == "paga":
        raise ErroApi("CONFLITO", "Ocorrência paga: reabra antes de excluir.", 409)
    db.session.delete(oc)
    db.session.commit()
    return "", 204


@bp.post("/ocorrencias/<oid>/reabrir")
@jwt_required()
def reabrir(oid: str):
    oc = buscar_ocorrencia(usuario_id(), parse_uuid(oid))
    reabrir_ocorrencia(oc)
    db.session.commit()
    return jsonify(oc.para_dict())
