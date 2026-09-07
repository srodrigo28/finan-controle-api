"""Autenticação: registro, login, refresh e perfil."""
from flask import Blueprint, jsonify
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required
from sqlalchemy import select

from app.erros import ErroApi
from app.esquemas.auth import (
    AtualizarEu,
    ConfirmarCodigo,
    ConfirmarToken,
    EsqueciSenha,
    Login,
    RedefinirSenha,
    Registrar,
)
from app.extensoes import db
from app.modelos import Usuario
from app.servicos import senha as servico_senha
from app.servicos import verificacao as servico_verificacao
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
    # A conta nasce com `email_verificado = false`: os tokens saem daqui só para
    # a tela do código conseguir chamar `/email/confirmar-codigo`. Todo o resto
    # da API responde 403 EMAIL_NAO_VERIFICADO até a confirmação.
    return jsonify({**_tokens(usuario), "verificacao": servico_verificacao.emitir_codigo(usuario)}), 201


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


@bp.post("/email/enviar-codigo")
@jwt_required()
def enviar_codigo():
    """Reenvia o código. Cooldown de 60 s → 429 AGUARDE_REENVIO."""
    return jsonify(servico_verificacao.emitir_codigo(usuario_atual()))


@bp.post("/email/confirmar-codigo")
@jwt_required()
def confirmar_codigo():
    """Exige sessão de propósito: o código pertence a uma conta específica.

    Sem o JWT a rota aceitaria "e-mail + código" de qualquer um, virando um
    oráculo para testar códigos contra endereços alheios. Quem chega aqui acabou
    de se cadastrar e já tem token.
    """
    dados = validar(ConfirmarCodigo)
    return jsonify(servico_verificacao.confirmar_por_codigo(usuario_atual(), dados.codigo))


@bp.post("/email/confirmar")
def confirmar_email():
    """Confirmação pelo link do e-mail — anônima: quem clica pode estar em outro aparelho."""
    dados = validar(ConfirmarToken)
    return jsonify(servico_verificacao.confirmar_por_token(dados.token))


@bp.post("/senha/esqueci")
def esqueci_senha():
    """Responde 200 mesmo se o e-mail não existir — diferenciar entregaria a lista de quem tem conta."""
    dados = validar(EsqueciSenha)
    resultado = servico_senha.esqueci(dados.email)
    corpo = {"mensagem": "Se este e-mail tiver uma conta, enviamos o link de redefinição."}
    if resultado.get("url"):  # só em TESTING
        corpo["url"] = resultado["url"]
    return jsonify(corpo)


@bp.post("/senha/redefinir")
def redefinir_senha():
    """Troca a senha e já devolve a sessão: quem redefiniu não precisa digitar de novo."""
    dados = validar(RedefinirSenha)
    usuario = servico_senha.redefinir(dados.token, dados.senha)
    return jsonify(_tokens(usuario))


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
