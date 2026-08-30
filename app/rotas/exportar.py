"""Exportação dos dados do usuário (CSV/JSON, sem paywall)."""
import csv
import io

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import select

from app.extensoes import db
from app.modelos import Categoria, Lancamento
from app.util import parse_data, usuario_id

bp = Blueprint("exportar", __name__, url_prefix="/exportar")


def _lancamentos():
    uid = usuario_id()
    consulta = select(Lancamento).where(Lancamento.usuario_id == uid)
    de = parse_data(request.args.get("de"), "de")
    ate = parse_data(request.args.get("ate"), "ate")
    if de:
        consulta = consulta.where(Lancamento.data >= de)
    if ate:
        consulta = consulta.where(Lancamento.data <= ate)
    lancs = db.session.scalars(consulta.order_by(Lancamento.data, Lancamento.criado_em)).all()
    nomes = {c.id: c.nome for c in db.session.scalars(select(Categoria).where(Categoria.usuario_id == uid)).all()}
    return lancs, nomes


@bp.get("/lancamentos.csv")
@jwt_required()
def csv_lancamentos():
    lancs, nomes = _lancamentos()
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\n")
    escritor.writerow(["data", "tipo", "valor", "categoria", "descricao", "forma_pagamento", "id"])
    for lc in lancs:
        escritor.writerow([
            lc.data.isoformat(),
            lc.tipo,
            f"{lc.valor:.2f}".replace(".", ","),
            nomes.get(lc.categoria_id, ""),
            lc.descricao,
            lc.forma_pagamento or "",
            str(lc.id),
        ])
    conteudo = "﻿" + buffer.getvalue()  # BOM para o Excel abrir com acentos
    return Response(
        conteudo,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=lancamentos.csv"},
    )


@bp.get("/lancamentos.json")
@jwt_required()
def json_lancamentos():
    lancs, nomes = _lancamentos()
    dados = []
    for lc in lancs:
        d = lc.para_dict()
        d["categoria"] = nomes.get(lc.categoria_id)
        dados.append(d)
    resposta = jsonify({"dados": dados, "total": len(dados)})
    resposta.headers["Content-Disposition"] = "attachment; filename=lancamentos.json"
    return resposta
