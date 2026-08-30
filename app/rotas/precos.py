"""Histórico de preços: último preço e autocomplete de itens."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import func, select

from app.erros import ErroApi
from app.extensoes import db
from app.modelos import PrecoHistorico
from app.util import normalizar_descricao, usuario_id

bp = Blueprint("precos", __name__, url_prefix="/precos")


@bp.get("/ultimo")
@jwt_required()
def ultimo():
    descricao = request.args.get("descricao", "").strip()
    if not descricao:
        raise ErroApi("VALIDACAO", "Informe descricao.", 422)
    registro = db.session.scalar(
        select(PrecoHistorico)
        .where(
            PrecoHistorico.usuario_id == usuario_id(),
            PrecoHistorico.descricao_normalizada == normalizar_descricao(descricao),
        )
        .order_by(PrecoHistorico.data.desc(), PrecoHistorico.criado_em.desc())
        .limit(1)
    )
    return jsonify(registro.para_dict() if registro else None)


@bp.get("/sugestoes")
@jwt_required()
def sugestoes():
    q = normalizar_descricao(request.args.get("q", ""))
    if len(q) < 1:
        return jsonify({"dados": []})
    uid = usuario_id()
    # Último registro de cada descrição normalizada que começa com o termo.
    ultimo_por_desc = (
        select(PrecoHistorico.descricao_normalizada, func.max(PrecoHistorico.criado_em).label("ultimo"))
        .where(PrecoHistorico.usuario_id == uid, PrecoHistorico.descricao_normalizada.like(f"{q}%"))
        .group_by(PrecoHistorico.descricao_normalizada)
        .subquery()
    )
    registros = db.session.scalars(
        select(PrecoHistorico)
        .join(
            ultimo_por_desc,
            (PrecoHistorico.descricao_normalizada == ultimo_por_desc.c.descricao_normalizada)
            & (PrecoHistorico.criado_em == ultimo_por_desc.c.ultimo),
        )
        .where(PrecoHistorico.usuario_id == uid)
        .order_by(PrecoHistorico.descricao_normalizada)
        .limit(10)
    ).all()
    return jsonify({
        "dados": [
            {"descricao": r.descricao, "categoria_id": str(r.categoria_id) if r.categoria_id else None, "valor_unitario": float(r.valor_unitario)}
            for r in registros
        ]
    })
