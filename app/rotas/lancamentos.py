"""Lançamentos gerais (despesa/receita) e anexos de comprovante."""
import os
import uuid

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import jwt_required
from sqlalchemy import func, or_, select
from werkzeug.utils import secure_filename

from app.erros import ErroApi, nao_encontrado
from app.esquemas.lancamento import AtualizarLancamento, CriarLancamento
from app.extensoes import db
from app.modelos import Anexo, Lancamento, SessaoCompra
from app.servicos.categorias import categoria_do_usuario
from app.util import dec, parse_data, parse_uuid, usuario_id, validar

bp = Blueprint("lancamentos", __name__, url_prefix="")

MIMES_PERMITIDOS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


def buscar_lancamento(lid: str) -> Lancamento:
    lanc = db.session.get(Lancamento, parse_uuid(lid))
    if lanc is None or lanc.usuario_id != usuario_id():
        raise nao_encontrado("Lançamento")
    return lanc


def _com_itens(lanc: Lancamento) -> dict:
    itens = None
    if lanc.sessao_id:
        sessao = db.session.get(SessaoCompra, lanc.sessao_id)
        if sessao is not None:
            itens = [i.para_dict() for i in sessao.itens if not i.removido]
    return lanc.para_dict(itens)


@bp.get("/lancamentos")
@jwt_required()
def listar():
    uid = usuario_id()
    a = request.args
    consulta = select(Lancamento).where(Lancamento.usuario_id == uid)
    de = parse_data(a.get("de"), "de")
    ate = parse_data(a.get("ate"), "ate")
    if de:
        consulta = consulta.where(Lancamento.data >= de)
    if ate:
        consulta = consulta.where(Lancamento.data <= ate)
    if a.get("tipo") in ("despesa", "receita"):
        consulta = consulta.where(Lancamento.tipo == a["tipo"])
    if a.get("categoria_id"):
        consulta = consulta.where(Lancamento.categoria_id == parse_uuid(a["categoria_id"], "categoria_id"))
    if a.get("busca"):
        termo = f"%{a['busca'].strip()}%"
        consulta = consulta.where(or_(Lancamento.descricao.ilike(termo)))

    try:
        pagina = max(int(a.get("pagina", 1)), 1)
        por_pagina = min(max(int(a.get("por_pagina", 50)), 1), 200)
    except ValueError:
        raise ErroApi("VALIDACAO", "pagina/por_pagina devem ser inteiros.", 422)

    total = db.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
    itens = db.session.scalars(
        consulta.order_by(Lancamento.data.desc(), Lancamento.criado_em.desc())
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
    ).all()
    return jsonify({"dados": [lc.para_dict() for lc in itens], "total": total, "pagina": pagina, "por_pagina": por_pagina})


@bp.post("/lancamentos")
@jwt_required()
def criar():
    uid = usuario_id()
    dados = validar(CriarLancamento)
    categoria_do_usuario(uid, dados.categoria_id)
    if dados.id is not None and db.session.get(Lancamento, dados.id) is not None:
        raise ErroApi("CONFLITO", "Já existe lançamento com este id.", 409)
    lanc = Lancamento(usuario_id=uid, **dados.model_dump(exclude_none=True))
    lanc.valor = dec(lanc.valor)
    db.session.add(lanc)
    db.session.commit()
    return jsonify(lanc.para_dict()), 201


@bp.get("/lancamentos/<lid>")
@jwt_required()
def detalhe(lid: str):
    return jsonify(_com_itens(buscar_lancamento(lid)))


@bp.patch("/lancamentos/<lid>")
@jwt_required()
def atualizar(lid: str):
    lanc = buscar_lancamento(lid)
    dados = validar(AtualizarLancamento)
    campos = dados.campos_enviados()
    if "categoria_id" in campos:
        categoria_do_usuario(lanc.usuario_id, campos["categoria_id"])
    if "valor" in campos and campos["valor"] is not None:
        campos["valor"] = dec(campos["valor"])
    for campo, valor in campos.items():
        setattr(lanc, campo, valor)
    db.session.commit()
    return jsonify(_com_itens(lanc))


@bp.delete("/lancamentos/<lid>")
@jwt_required()
def excluir(lid: str):
    lanc = buscar_lancamento(lid)
    for anexo in lanc.anexos:
        _remover_arquivo(anexo)
    db.session.delete(lanc)
    db.session.commit()
    return "", 204


# ---------- Anexos ----------

def _remover_arquivo(anexo: Anexo) -> None:
    try:
        os.remove(os.path.join(current_app.config["UPLOAD_DIR"], anexo.caminho))
    except OSError:
        pass


@bp.post("/lancamentos/<lid>/anexos")
@jwt_required()
def enviar_anexo(lid: str):
    lanc = buscar_lancamento(lid)
    arquivo = request.files.get("arquivo")
    if arquivo is None or not arquivo.filename:
        raise ErroApi("VALIDACAO", "Envie o campo multipart 'arquivo'.", 422)
    mime = (arquivo.mimetype or "").lower()
    if mime not in MIMES_PERMITIDOS:
        raise ErroApi("VALIDACAO", "Tipo de arquivo não permitido (jpg, png, webp ou pdf).", 422, {"tipo_mime": mime})

    conteudo = arquivo.read()
    if len(conteudo) > current_app.config["MAX_CONTENT_LENGTH"]:
        raise ErroApi("ARQUIVO_GRANDE", "Arquivo excede 8 MB.", 413)
    if not conteudo:
        raise ErroApi("VALIDACAO", "Arquivo vazio.", 422)

    nome_disco = f"{uuid.uuid4()}{MIMES_PERMITIDOS[mime]}"
    pasta = os.path.join(current_app.config["UPLOAD_DIR"], str(lanc.usuario_id))
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, nome_disco), "wb") as f:
        f.write(conteudo)

    anexo = Anexo(
        lancamento_id=lanc.id,
        nome=secure_filename(arquivo.filename)[:200] or nome_disco,
        caminho=f"{lanc.usuario_id}/{nome_disco}",
        tipo_mime=mime,
        tamanho=len(conteudo),
    )
    db.session.add(anexo)
    db.session.commit()
    return jsonify(anexo.para_dict()), 201


def _buscar_anexo(aid: str) -> Anexo:
    anexo = db.session.get(Anexo, parse_uuid(aid))
    if anexo is None or anexo.lancamento.usuario_id != usuario_id():
        raise nao_encontrado("Anexo")
    return anexo


@bp.delete("/anexos/<aid>")
@jwt_required()
def excluir_anexo(aid: str):
    anexo = _buscar_anexo(aid)
    _remover_arquivo(anexo)
    db.session.delete(anexo)
    db.session.commit()
    return "", 204


@bp.get("/anexos/<aid>/arquivo")
@jwt_required()
def baixar_anexo(aid: str):
    anexo = _buscar_anexo(aid)
    caminho = os.path.join(current_app.config["UPLOAD_DIR"], anexo.caminho)
    if not os.path.isfile(caminho):
        raise nao_encontrado("Arquivo do anexo")
    return send_file(caminho, mimetype=anexo.tipo_mime, download_name=anexo.nome, as_attachment=False)
