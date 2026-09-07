"""Confirmação de e-mail no cadastro: código de 4 dígitos + link, padrão 99dev.

Molde: `app/services/email_verification_service.py` do SUWAVE.
Ver `docs/prompts/6-setembro-validacao-smtp-esqueci-senha.md`.
"""
import secrets
from datetime import timedelta

from flask import current_app
from sqlalchemy import select

from app.erros import ErroApi
from app.extensoes import db
from app.modelos import CodigoVerificacao, Usuario
from app.modelos.verificacao import CADASTRO
from app.servicos import email as servico_email
from app.util import agora, gerar_codigo, gerar_token, hash_token

DIGITOS = 4


def emitir_codigo(usuario: Usuario) -> dict:
    """Gera código + token, grava e dispara o e-mail.

    Reenviar **invalida o código anterior**: só o último registro aberto é aceito
    na confirmação. Dois códigos válidos ao mesmo tempo dobrariam a superfície de
    ataque sem ajudar ninguém.
    """
    if usuario.email_verificado:
        raise ErroApi("EMAIL_JA_VERIFICADO", "Esta conta já está confirmada.", 409)

    espera = espera_restante(usuario, CADASTRO, current_app.config["EMAIL_VERIFICATION_RESEND_SECONDS"])
    if espera:
        raise ErroApi(
            "AGUARDE_REENVIO",
            f"Aguarde {espera} segundos para pedir outro código.",
            429,
            {"reenvio_em": espera},
        )

    horas = current_app.config["EMAIL_VERIFICATION_TOKEN_EXPIRES_HOURS"]
    codigo, token = gerar_codigo(DIGITOS), gerar_token()
    invalidar_abertos(usuario, CADASTRO)
    db.session.add(
        CodigoVerificacao(
            usuario_id=usuario.id,
            email=usuario.email,
            finalidade=CADASTRO,
            codigo_hash=hash_token(codigo),
            token_hash=hash_token(token),
            expira_em=agora() + timedelta(hours=horas),
        )
    )
    db.session.commit()

    url = f"{current_app.config['APP_URL'].rstrip('/')}/confirmar-email?token={token}"
    servico_email.enviar_codigo_cadastro(
        usuario.email, usuario.nome, codigo, url, horas, current_app.config["EMAIL_VERIFICATION_MAX_ATTEMPTS"]
    )

    return {
        "email": usuario.email,
        "expira_em_horas": horas,
        "reenvio_em": current_app.config["EMAIL_VERIFICATION_RESEND_SECONDS"],
        # Código e link só voltam na resposta em TESTE. Em produção eles existem
        # no e-mail e em nenhum outro lugar, senão a verificação não verifica nada.
        "codigo": codigo if current_app.config.get("TESTING") else None,
        "url": url if current_app.config.get("TESTING") else None,
    }


def confirmar_por_codigo(usuario: Usuario, codigo: str) -> dict:
    """Confirma pelos dígitos que chegaram na caixa de entrada."""
    codigo = (codigo or "").strip()
    if not codigo.isdigit() or len(codigo) != DIGITOS:
        raise ErroApi("CODIGO_INVALIDO", f"Digite os {DIGITOS} números do código que enviamos por e-mail.", 400)
    if usuario.email_verificado:
        raise ErroApi("EMAIL_JA_VERIFICADO", "Esta conta já está confirmada.", 409)

    # O código mestre vem ANTES da busca pelo registro: é o único caminho que
    # funciona quando NENHUM código foi emitido — o estado exato de um ambiente
    # em que o SMTP ainda não sai.
    if _e_codigo_mestre(codigo):
        current_app.logger.warning(
            "CÓDIGO MESTRE de verificação usado por %s — atalho de teste ligado", usuario.email
        )
        return _marcar_confirmado(usuario, None)

    registro = _ultimo_aberto(usuario, CADASTRO)
    if registro is None or registro.codigo_hash is None:
        raise ErroApi("CODIGO_NAO_ENCONTRADO", "Não há código ativo. Peça um novo código.", 400)
    if registro.expira_em < agora():
        raise ErroApi("CODIGO_EXPIRADO", "Este código expirou. Peça um novo.", 400)

    maximo = current_app.config["EMAIL_VERIFICATION_MAX_ATTEMPTS"]
    if registro.tentativas >= maximo:
        raise ErroApi("CODIGO_BLOQUEADO", "Você errou o código muitas vezes. Peça um novo código.", 429)

    if not secrets.compare_digest(registro.codigo_hash, hash_token(codigo)):
        # O erro é contado ANTES de responder: se o incremento viesse depois, quem
        # corta a conexão a cada tentativa nunca gastaria chance e o teto viraria enfeite.
        registro.tentativas += 1
        db.session.commit()
        restantes = max(0, maximo - registro.tentativas)
        recado = (
            f"Código incorreto. Você tem mais {restantes} tentativa(s)."
            if restantes
            else "Código incorreto. Peça um novo código."
        )
        raise ErroApi("CODIGO_INVALIDO", recado, 400, {"tentativas_restantes": restantes})

    return _marcar_confirmado(usuario, registro)


def confirmar_por_token(token: str) -> dict:
    """Confirma pelo link do e-mail. Mesmo desfecho do código."""
    registro = db.session.scalar(
        select(CodigoVerificacao).where(
            CodigoVerificacao.token_hash == hash_token(token or ""),
            CodigoVerificacao.finalidade == CADASTRO,
        )
    )
    if registro is None:
        raise ErroApi("TOKEN_INVALIDO", "Link de confirmação inválido.", 404)
    if registro.usado_em is not None:
        raise ErroApi("TOKEN_USADO", "Este link já foi usado.", 409)
    if registro.expira_em < agora():
        raise ErroApi("TOKEN_EXPIRADO", "Este link expirou. Peça um novo código.", 410)

    usuario = db.session.get(Usuario, registro.usuario_id)
    if usuario is None:
        raise ErroApi("NAO_ENCONTRADO", "Usuário não encontrado.", 404)
    if usuario.email != registro.email:
        raise ErroApi("TOKEN_INVALIDO", "Este link não corresponde ao e-mail atual da conta.", 400)
    if usuario.email_verificado:
        raise ErroApi("EMAIL_JA_VERIFICADO", "Esta conta já está confirmada.", 409)

    return _marcar_confirmado(usuario, registro)


def _marcar_confirmado(usuario: Usuario, registro: CodigoVerificacao | None) -> dict:
    """Efetiva a confirmação. `registro=None` é o caminho do código mestre.

    Os dois caminhos terminam iguais de propósito: uma conta confirmada pelo
    atalho precisa sair com os mesmos campos da confirmada de verdade, senão
    desligar o atalho depois deixaria um rastro de contas meio confirmadas.
    """
    usuario.email_verificado = True
    usuario.email_verificado_em = agora()
    if registro is not None:
        registro.usado_em = usuario.email_verificado_em
    db.session.commit()
    return usuario.para_dict()


def _e_codigo_mestre(codigo: str) -> bool:
    """Atalho da fase de teste: um código fixo que confirma qualquer conta.

    Desligado (`EMAIL_VERIFICATION_TEST_CODE` vazio) é o estado de produção. Um
    valor mal formado também desliga, com aviso no log: um atalho que *parece*
    ligado e não funciona custa meia hora de investigação.
    """
    mestre = (current_app.config.get("EMAIL_VERIFICATION_TEST_CODE") or "").strip()
    if not mestre:
        return False
    if not (mestre.isdigit() and len(mestre) == DIGITOS):
        current_app.logger.warning("EMAIL_VERIFICATION_TEST_CODE ignorado: precisa ter %s dígitos", DIGITOS)
        return False
    return secrets.compare_digest(mestre, codigo)


def _ultimo_aberto(usuario: Usuario, finalidade: str) -> CodigoVerificacao | None:
    return db.session.scalar(
        select(CodigoVerificacao)
        .where(
            CodigoVerificacao.usuario_id == usuario.id,
            CodigoVerificacao.email == usuario.email,
            CodigoVerificacao.finalidade == finalidade,
            CodigoVerificacao.usado_em.is_(None),
        )
        .order_by(CodigoVerificacao.criado_em.desc())
        .limit(1)
    )


def invalidar_abertos(usuario: Usuario, finalidade: str) -> None:
    """Marca como usados os códigos anteriores do mesmo tipo."""
    for antigo in db.session.scalars(
        select(CodigoVerificacao).where(
            CodigoVerificacao.usuario_id == usuario.id,
            CodigoVerificacao.finalidade == finalidade,
            CodigoVerificacao.usado_em.is_(None),
        )
    ):
        antigo.usado_em = agora()


def espera_restante(usuario: Usuario, finalidade: str, segundos: int) -> int:
    """Segundos que faltam para poder pedir outro envio (0 = pode enviar).

    O cooldown sai do `criado_em` do último registro — não precisa de coluna
    extra no usuário e vale para os dois fluxos.
    """
    ultimo = db.session.scalar(
        select(CodigoVerificacao)
        .where(
            CodigoVerificacao.usuario_id == usuario.id,
            CodigoVerificacao.finalidade == finalidade,
        )
        .order_by(CodigoVerificacao.criado_em.desc())
        .limit(1)
    )
    if ultimo is None:
        return 0
    passados = (agora() - ultimo.criado_em).total_seconds()
    return max(0, int(segundos - passados) + 1) if passados < segundos else 0
