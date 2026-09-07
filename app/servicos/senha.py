"""Esqueci minha senha: link com token opaco, uso único.

Molde: `auth_service.forgot_password` / `reset_password` do SUWAVE.
Ver `docs/prompts/6-setembro-validacao-smtp-esqueci-senha.md`.

**Por que link e não código de 4 dígitos.** Esta rota é anônima. Uma rota anônima
que aceitasse "e-mail + 4 dígitos" viraria um oráculo para testar códigos contra
endereços alheios; o código curto do cadastro só é seguro porque lá o JWT já
amarra o código a uma conta específica.
"""
from datetime import timedelta

from flask import current_app
from sqlalchemy import select

from app.erros import ErroApi
from app.extensoes import db
from app.modelos import CodigoVerificacao, Usuario
from app.modelos.verificacao import SENHA
from app.servicos import email as servico_email
from app.servicos.verificacao import espera_restante, invalidar_abertos
from app.util import agora, gerar_token, hash_token


def esqueci(email: str) -> dict:
    """Emite o link de redefinição. **Nunca conta se o e-mail existe.**

    A rota responde 200 de qualquer jeito: diferenciar entregaria uma lista de
    quem tem conta no sistema. (O SUWAVE devolve 404 aqui — divergência
    consciente deste padrão, anotada no prompt.)
    """
    email = (email or "").strip().lower()
    usuario = db.session.scalar(select(Usuario).where(Usuario.email == email))
    resposta: dict = {"email": email, "url": None}
    if usuario is None:
        current_app.logger.info("Pedido de redefinição para e-mail sem conta: %s", email)
        return resposta

    segundos = current_app.config["PASSWORD_RESET_RESEND_SECONDS"]
    if espera_restante(usuario, SENHA, segundos):
        # Silencioso também no cooldown: um 429 aqui contaria que a conta existe.
        current_app.logger.info("Pedido de redefinição dentro do cooldown para %s", email)
        return resposta

    horas = current_app.config["PASSWORD_RESET_TOKEN_EXPIRES_HOURS"]
    token = gerar_token()
    invalidar_abertos(usuario, SENHA)
    db.session.add(
        CodigoVerificacao(
            usuario_id=usuario.id,
            email=usuario.email,
            finalidade=SENHA,
            token_hash=hash_token(token),
            expira_em=agora() + timedelta(hours=horas),
        )
    )
    db.session.commit()

    url = f"{current_app.config['APP_URL'].rstrip('/')}/redefinir-senha?token={token}"
    servico_email.enviar_reset_senha(usuario.email, usuario.nome, url, horas)
    # O link só volta na resposta em TESTE — em produção ele existe no e-mail e
    # em nenhum outro lugar.
    return {"email": email, "url": url if current_app.config.get("TESTING") else None}


def redefinir(token: str, nova_senha: str) -> Usuario:
    registro = db.session.scalar(
        select(CodigoVerificacao).where(
            CodigoVerificacao.token_hash == hash_token(token or ""),
            CodigoVerificacao.finalidade == SENHA,
        )
    )
    if registro is None:
        raise ErroApi("TOKEN_INVALIDO", "Link inválido. Peça outro e-mail de redefinição.", 404)
    if registro.usado_em is not None:
        raise ErroApi("TOKEN_USADO", "Este link já foi usado. Peça outro e-mail de redefinição.", 409)
    if registro.expira_em < agora():
        raise ErroApi("TOKEN_EXPIRADO", "Este link expirou. Peça outro e-mail de redefinição.", 410)

    usuario = db.session.get(Usuario, registro.usuario_id)
    if usuario is None:
        raise ErroApi("NAO_ENCONTRADO", "Usuário não encontrado.", 404)

    usuario.definir_senha(nova_senha)
    # Quem chegou aqui provou que lê a caixa de entrada — a conta fica confirmada
    # de tabela, e ninguém trava na tela do código depois de redefinir a senha.
    if not usuario.email_verificado:
        usuario.email_verificado = True
        usuario.email_verificado_em = agora()
    registro.usado_em = agora()
    # Os outros links de senha em aberto morrem junto: um pedido feito duas vezes
    # não pode deixar um segundo link vivo depois da troca.
    invalidar_abertos(usuario, SENHA)
    db.session.commit()
    return usuario
