"""CRUD de categorias (arquivar em vez de excluir)."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import func, select

from app.erros import ErroApi, nao_encontrado
from app.esquemas.categoria import AtualizarCategoria, CriarCategoria, Reordenar
from app.extensoes import db
from app.modelos import Categoria
from app.servicos.categorias import categoria_do_usuario
from app.util import parse_uuid, usuario_id, validar
from app.servicos.plano import exige_plano_ativo

bp = Blueprint("categorias", __name__, url_prefix="/categorias")


def _buscar(cid: str) -> Categoria:
    cat = db.session.get(Categoria, parse_uuid(cid))
    if cat is None or cat.usuario_id != usuario_id():
        raise nao_encontrado("Categoria")
    return cat


@bp.get("")
@jwt_required()
def listar():
    consulta = select(Categoria).where(Categoria.usuario_id == usuario_id())
    if request.args.get("incluir_arquivadas", "0") != "1":
        consulta = consulta.where(Categoria.arquivada.is_(False))
    cats = db.session.scalars(consulta.order_by(Categoria.ordem, Categoria.nome)).all()
    return jsonify({"dados": [c.para_dict() for c in cats]})


@bp.post("")
@jwt_required()
@exige_plano_ativo
def criar():
    uid = usuario_id()
    dados = validar(CriarCategoria)
    if dados.pai_id is not None:
        pai = categoria_do_usuario(uid, dados.pai_id)
        if pai.pai_id is not None:
            raise ErroApi("VALIDACAO", "Só é permitido um nível de subcategoria.", 422, {"pai_id": "já é subcategoria"})
    if dados.id is not None and db.session.get(Categoria, dados.id) is not None:
        raise ErroApi("CONFLITO", "Já existe categoria com este id.", 409)
    ordem = db.session.scalar(select(func.coalesce(func.max(Categoria.ordem), -1)).where(Categoria.usuario_id == uid)) + 1
    cat = Categoria(usuario_id=uid, ordem=ordem, **dados.model_dump(exclude_none=True))
    db.session.add(cat)
    db.session.commit()
    return jsonify(cat.para_dict()), 201


@bp.patch("/<cid>")
@jwt_required()
def atualizar(cid: str):
    cat = _buscar(cid)
    dados = validar(AtualizarCategoria)
    campos = dados.campos_enviados()
    if "pai_id" in campos and campos["pai_id"] is not None:
        if campos["pai_id"] == cat.id:
            raise ErroApi("VALIDACAO", "Categoria não pode ser pai de si mesma.", 422)
        pai = categoria_do_usuario(cat.usuario_id, campos["pai_id"])
        if pai.pai_id is not None:
            raise ErroApi("VALIDACAO", "Só é permitido um nível de subcategoria.", 422)
    for campo, valor in campos.items():
        setattr(cat, campo, valor)
    db.session.commit()
    return jsonify(cat.para_dict())


@bp.delete("/<cid>")
@jwt_required()
def arquivar(cid: str):
    cat = _buscar(cid)
    cat.arquivada = True
    # Subcategorias acompanham o pai.
    for sub in db.session.scalars(select(Categoria).where(Categoria.pai_id == cat.id)).all():
        sub.arquivada = True
    db.session.commit()
    return "", 204


@bp.post("/reordenar")
@jwt_required()
def reordenar():
    uid = usuario_id()
    dados = validar(Reordenar)
    cats = {c.id: c for c in db.session.scalars(select(Categoria).where(Categoria.usuario_id == uid)).all()}
    for posicao, cid in enumerate(dados.ids):
        cat = cats.get(cid)
        if cat is None:
            raise ErroApi("VALIDACAO", "Categoria inválida na lista.", 422, {"ids": str(cid)})
        cat.ordem = posicao
    db.session.commit()
    return "", 204
