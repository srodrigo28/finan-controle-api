"""Autenticação: registro, login, refresh e perfil."""
from flask import Blueprint, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required
from sqlalchemy import select

from app.erros import ErroApi
from app.esquemas.auth import AtualizarEu, Login, Registrar
from app.extensoes import db
from app.modelos import Usuario
from app.servicos.categorias import criar_categorias_padrao
from app.util import usuario_id, validar

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _tokens(usuario: Usuario) -> dict:
    ident = str(usuario.id)
    return {
        "usuario": usuario.para_dict(),
        "access_token": create_access_token(identity=ident),
        "refresh_token": create_refresh_token(identity=ident),
    }


def usuario_atual() -> Usuario:
    usuario = db.session.get(Usuario, usuario_id())
    if usuario is None:
        raise ErroApi("NAO_AUTENTICADO", "Usuário não existe mais.", 401)
    return usuario


@bp.post("/registrar")
def registrar():
    dados = validar(Registrar)
    email = dados.email.lower()
    if db.session.scalar(select(Usuario).where(Usuario.email == email)):
        raise ErroApi("CONFLITO", "E-mail já cadastrado.", 409, {"email": "já cadastrado"})
    usuario = Usuario(nome=dados.nome, email=email)
    usuario.definir_senha(dados.senha)
    db.session.add(usuario)
    db.session.flush()
    criar_categorias_padrao(usuario.id)
    db.session.commit()
    return jsonify(_tokens(usuario)), 201


@bp.post("/login")
def login():
    dados = validar(Login)
    usuario = db.session.scalar(select(Usuario).where(Usuario.email == dados.email.lower()))
    if usuario is None or not usuario.verificar_senha(dados.senha):
        raise ErroApi("CREDENCIAIS_INVALIDAS", "E-mail ou senha incorretos.", 401)
    return jsonify(_tokens(usuario))


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    usuario = usuario_atual()
    return jsonify({"access_token": create_access_token(identity=str(usuario.id))})


@bp.get("/eu")
@jwt_required()
def eu():
    return jsonify(usuario_atual().para_dict())


@bp.patch("/eu")
@jwt_required()
def atualizar_eu():
    usuario = usuario_atual()
    dados = validar(AtualizarEu)
    for campo, valor in dados.campos_enviados().items():
        setattr(usuario, campo, valor)
    db.session.commit()
    return jsonify(usuario.para_dict())
