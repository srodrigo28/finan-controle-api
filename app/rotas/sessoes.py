"""Modo Mercado: sessões de compra, itens do carrinho, fechamento e sincronização."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import select

from app.erros import ErroApi, nao_encontrado
from app.esquemas.sessao import AtualizarItem, AtualizarSessao, CriarItem, CriarSessao, FecharSessao, Sincronizar
from app.extensoes import db
from app.modelos import ItemCompra, SessaoCompra
from app.servicos.categorias import categoria_do_usuario
from app.servicos.sessoes import buscar_sessao, fechar_sessao, sincronizar_sessoes
from app.util import agora, dec, parse_uuid, usuario_id, validar
from app.servicos.plano import garantir_plano_ativo

bp = Blueprint("sessoes", __name__, url_prefix="/sessoes")


def _sessao(sid: str) -> SessaoCompra:
    return buscar_sessao(usuario_id(), parse_uuid(sid))


def _sessao_aberta(sid: str) -> SessaoCompra:
    sessao = _sessao(sid)
    if sessao.status != "aberta":
        raise ErroApi("CONFLITO", "Sessão não está aberta.", 409)
    return sessao


def _item(sessao: SessaoCompra, item_id: str) -> ItemCompra:
    iid = parse_uuid(item_id, "item_id")
    for item in sessao.itens:
        if item.id == iid:
            return item
    raise nao_encontrado("Item")


@bp.get("")
@jwt_required()
def listar():
    consulta = select(SessaoCompra).where(SessaoCompra.usuario_id == usuario_id())
    status = request.args.get("status")
    if status:
        consulta = consulta.where(SessaoCompra.status == status)
    sessoes = db.session.scalars(consulta.order_by(SessaoCompra.aberta_em.desc()).limit(200)).all()
    return jsonify({"dados": [s.para_dict(com_itens=False) for s in sessoes]})


@bp.post("")
@jwt_required()
def abrir():
    uid = usuario_id()
    dados = validar(CriarSessao)
    if dados.id is not None:
        existente = db.session.get(SessaoCompra, dados.id)
        if existente is not None:
            if existente.usuario_id != uid:
                raise ErroApi("CONFLITO", "Id já utilizado.", 409)
            return jsonify(existente.para_dict()), 200  # idempotente
    # O gate fica aqui, e não no decorator, de propósito: uma sessão que já existe (reenvio do app
    # offline) precisa passar mesmo com o teste vencido — ela é dado que o usuário já registrou.
    garantir_plano_ativo()
    sessao = SessaoCompra(usuario_id=uid, **dados.model_dump(exclude_none=True))
    db.session.add(sessao)
    db.session.commit()
    return jsonify(sessao.para_dict()), 201


@bp.get("/<sid>")
@jwt_required()
def detalhe(sid: str):
    return jsonify(_sessao(sid).para_dict())


@bp.patch("/<sid>")
@jwt_required()
def atualizar(sid: str):
    sessao = _sessao_aberta(sid)
    dados = validar(AtualizarSessao)
    for campo, valor in dados.campos_enviados().items():
        setattr(sessao, campo, valor)
    db.session.commit()
    return jsonify(sessao.para_dict())


@bp.post("/<sid>/itens")
@jwt_required()
def adicionar_item(sid: str):
    sessao = _sessao_aberta(sid)
    dados = validar(CriarItem)
    categoria_do_usuario(sessao.usuario_id, dados.categoria_id)
    if dados.id is not None:
        existente = db.session.get(ItemCompra, dados.id)
        if existente is not None:
            if existente.sessao_id != sessao.id:
                raise ErroApi("CONFLITO", "Id de item já utilizado.", 409)
            return jsonify(existente.para_dict()), 200  # idempotente
    item = ItemCompra(
        sessao_id=sessao.id,
        id=dados.id,
        descricao=dados.descricao,
        categoria_id=dados.categoria_id,
        valor_unitario=dec(dados.valor_unitario),
        quantidade=dec(dados.quantidade, 3),
    )
    db.session.add(item)
    sessao.atualizado_em = agora()
    db.session.commit()
    return jsonify(item.para_dict()), 201


@bp.patch("/<sid>/itens/<item_id>")
@jwt_required()
def atualizar_item(sid: str, item_id: str):
    sessao = _sessao_aberta(sid)
    item = _item(sessao, item_id)
    dados = validar(AtualizarItem)
    campos = dados.campos_enviados()
    if "categoria_id" in campos:
        categoria_do_usuario(sessao.usuario_id, campos["categoria_id"])
    if campos.get("valor_unitario") is not None:
        campos["valor_unitario"] = dec(campos["valor_unitario"])
    if campos.get("quantidade") is not None:
        campos["quantidade"] = dec(campos["quantidade"], 3)
    for campo, valor in campos.items():
        setattr(item, campo, valor)
    sessao.atualizado_em = agora()
    db.session.commit()
    return jsonify(item.para_dict())


@bp.delete("/<sid>/itens/<item_id>")
@jwt_required()
def remover_item(sid: str, item_id: str):
    sessao = _sessao_aberta(sid)
    item = _item(sessao, item_id)
    item.removido = True
    sessao.atualizado_em = agora()
    db.session.commit()
    return "", 204


@bp.post("/<sid>/fechar")
@jwt_required()
def fechar(sid: str):
    sessao = _sessao_aberta(sid)
    dados = validar(FecharSessao)
    lancamento = fechar_sessao(
        sessao, sessao.usuario_id, dados.total_pago, dados.motivo_divergencia, dados.categoria_id, dados.forma_pagamento
    )
    db.session.commit()
    return jsonify({"sessao": sessao.para_dict(), "lancamento": lancamento.para_dict()})


@bp.post("/<sid>/abandonar")
@jwt_required()
def abandonar(sid: str):
    sessao = _sessao_aberta(sid)
    sessao.status = "abandonada"
    sessao.fechada_em = agora()
    sessao.total_carrinho = sessao.calcular_total()
    db.session.commit()
    return "", 204


@bp.post("/sincronizar")
@jwt_required()
def sincronizar():
    dados = validar(Sincronizar)
    sessoes = sincronizar_sessoes(usuario_id(), dados.sessoes)
    db.session.commit()
    return jsonify({"sessoes": [s.para_dict() for s in sessoes]})
