"""Métricas diária, semanal e mensal."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.extensoes import db
from app.rotas.auth import usuario_atual
from app.servicos import insights as svc_insights
from app.servicos import metricas as svc
from app.servicos.tempo import hoje, parse_mes, segunda_feira
from app.util import parse_data

bp = Blueprint("metricas", __name__, url_prefix="/metricas")


@bp.get("/diario")
@jwt_required()
def diario():
    dia = parse_data(request.args.get("data"), "data", hoje())
    return jsonify(svc.diario(usuario_atual(), dia))


@bp.get("/semanal")
@jwt_required()
def semanal():
    inicio = parse_data(request.args.get("inicio"), "inicio", segunda_feira(hoje()))
    return jsonify(svc.semanal(usuario_atual(), inicio))


@bp.get("/mensal")
@jwt_required()
def mensal():
    ano, mes = parse_mes(request.args.get("mes"))
    resultado = svc.mensal(usuario_atual(), ano, mes)
    db.session.commit()  # gerar_ocorrencias pode ter criado registros
    return jsonify(resultado)


@bp.get("/insights")
@jwt_required()
def insights():
    """Frases automáticas da semana: variações por categoria, preço de itens, orçamento, contas."""
    inicio = parse_data(request.args.get("inicio"), "inicio", segunda_feira(hoje()))
    resultado = svc_insights.gerar(usuario_atual(), inicio)
    db.session.commit()  # gerar_ocorrencias pode ter criado registros
    return jsonify(resultado)
