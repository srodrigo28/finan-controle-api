"""Importação por IA: foto ou PDF → rascunho de lançamentos → revisão → confirmação."""
import os

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import jwt_required

from app.erros import nao_encontrado
from app.esquemas.importacao import AtualizarRascunho
from app.servicos import importacoes as servico
from app.servicos.plano import exige_plano_ativo
from app.servicos.tempo import hoje
from app.util import iso, parse_uuid, usuario_id, validar

bp = Blueprint("importacoes", __name__, url_prefix="")


def _buscar(iid: str, travar: bool = False):
    imp = servico.buscar(usuario_id(), parse_uuid(iid), travar=travar)
    servico.soltar_se_presa(imp)
    return imp


@bp.post("/importacoes")
@jwt_required()
@exige_plano_ativo
def criar():
    forcar = request.args.get("forcar") in ("1", "true")
    imp, anterior = servico.criar(usuario_id(), request.files.get("arquivo"), forcar=forcar)
    servico.disparar_leitura(imp)
    corpo = imp.para_dict()
    corpo["duplicada_de"] = (
        {"id": str(anterior.id), "criado_em": iso(anterior.criado_em), "estado": anterior.estado} if anterior else None
    )
    return jsonify(corpo), 202


@bp.get("/importacoes")
@jwt_required()
def listar():
    return jsonify({"dados": [i.para_dict() for i in servico.listar(usuario_id())]})


@bp.get("/importacoes/<iid>")
@jwt_required()
def detalhe(iid: str):
    return jsonify(_buscar(iid).para_dict())


@bp.get("/importacoes/<iid>/arquivo")
@jwt_required()
def arquivo(iid: str):
    imp = _buscar(iid)
    caminho = servico.caminho_arquivo(imp)
    if not os.path.isfile(caminho):
        raise nao_encontrado("Arquivo original")
    resposta = send_file(caminho, mimetype=imp.tipo_mime, download_name=imp.nome, as_attachment=False)
    # Extrato e fatura são dados sensíveis, e a origem 99dev.pro é compartilhada com outros apps.
    resposta.headers["Cache-Control"] = "private, no-store"
    resposta.headers["X-Content-Type-Options"] = "nosniff"
    return resposta


@bp.patch("/importacoes/<iid>")
@jwt_required()
def atualizar(iid: str):
    imp = _buscar(iid, travar=True)
    servico.atualizar_rascunho(imp, validar(AtualizarRascunho).linhas)
    return jsonify(imp.para_dict())


@bp.post("/importacoes/<iid>/confirmar")
@jwt_required()
@exige_plano_ativo
def confirmar(iid: str):
    imp = _buscar(iid, travar=True)
    corpo = request.get_json(silent=True) or {}
    linhas = validar(AtualizarRascunho, corpo).linhas if "linhas" in corpo else None
    criados, ocorrencias = servico.confirmar(imp, linhas)
    h = hoje()
    return jsonify({
        "importacao": imp.para_dict(),
        "lancamentos": [l.para_dict() for l in criados],
        "ocorrencias": [o.para_dict(h) for o in ocorrencias],
    })


@bp.post("/importacoes/<iid>/reler")
@jwt_required()
def reler(iid: str):
    imp = _buscar(iid, travar=True)
    servico.reler(imp)
    return jsonify(imp.para_dict()), 202


@bp.post("/importacoes/<iid>/senha")
@jwt_required()
def senha(iid: str):
    """Senha do PDF protegido: abre uma cópia só para a leitura e não é guardada."""
    imp = _buscar(iid, travar=True)
    corpo = request.get_json(silent=True) or {}
    valor = corpo.get("senha")
    servico.informar_senha(imp, valor if isinstance(valor, str) else "")
    return jsonify(imp.para_dict()), 202


@bp.post("/importacoes/<iid>/descartar")
@jwt_required()
def descartar(iid: str):
    imp = _buscar(iid, travar=True)
    servico.descartar(imp)
    return jsonify(imp.para_dict())
