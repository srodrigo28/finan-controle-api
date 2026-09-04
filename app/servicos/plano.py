"""Limite de plano: o que só vale enquanto o teste (ou a assinatura) está ativo.

Regra do produto: nos 30 dias de teste **nada** é bloqueado. A partir do dia 31, trava-se apenas a
criação de coisa nova — ver, editar, excluir, exportar e sincronizar o que já existe continua livre,
sempre. Dado do usuário é do usuário.
"""
from functools import wraps

from flask_jwt_extended import verify_jwt_in_request

from app.erros import ErroApi
from app.extensoes import db
from app.modelos import Usuario
from app.util import usuario_id

MENSAGEM = "Seu teste grátis terminou. Assine o Finan Completo para registrar coisas novas — o que já está no app continua seu."


def plano_ativo() -> bool:
    usuario = db.session.get(Usuario, usuario_id())
    return bool(usuario and usuario.teste_ativo)


def garantir_plano_ativo() -> None:
    """Levanta 402 se o teste expirou. Use dentro da rota quando o bloqueio for condicional."""
    if not plano_ativo():
        raise ErroApi("TESTE_EXPIRADO", MENSAGEM, 402)


def exige_plano_ativo(f):
    """Decorator para rotas de criação. Vai **abaixo** de `@jwt_required()`."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        verify_jwt_in_request()
        garantir_plano_ativo()
        return f(*args, **kwargs)

    return wrapper
