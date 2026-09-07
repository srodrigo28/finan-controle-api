"""Diz se o e-mail do Finan consegue SAIR — sem depender da caixa de entrada.

    python scripts/checar_smtp.py                          # so autentica no SMTP
    python scripts/checar_smtp.py --enviar meu@email.com   # manda um de verdade

Por que existe
--------------
Porte do `scripts/checar_smtp.py` do SUWAVE. La, em 26/08/2026, a senha de app do
Gmail estava revogada e a API passou semanas sem enviar um unico codigo: o envio
roda em thread e a excecao e engolida de proposito (cadastro nao pode cair por
causa de e-mail), entao a unica prova de que o canal funciona e ir conferir.

O que ele responde, em ordem
----------------------------
1. a configuracao existe? (`MAIL_HOST` vazio faz a API so logar e seguir)
2. a porta 587 sai desta maquina? (STARTTLS)
3. o Gmail aceita a credencial? (`535 5.7.8` = senha de app revogada)
4. `APP_URL` aponta para o front que tem `/confirmar-email` e `/redefinir-senha`?

Rode DE DENTRO do container em producao (`docker exec -it finan-api python
scripts/checar_smtp.py`): o `.env` da maquina de dev nao e o `.env.deploy` que a
producao le, e ja foi essa diferenca que escondeu o problema no SUWAVE.

A senha nunca e impressa — so a impressao digital, para comparar dois ambientes
sem expor o segredo.
"""
import argparse
import hashlib
import logging
import smtplib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402


def _impressao(valor: str) -> str:
    if not valor:
        return "(vazio)"
    return f"{hashlib.sha256(valor.encode()).hexdigest()[:8]} ({len(valor)} chars)"


def main() -> int:
    parser = argparse.ArgumentParser(description="Checa o canal de e-mail da API Finan.")
    parser.add_argument("--enviar", metavar="DESTINO", help="envia um e-mail de teste de verdade para este endereco")
    args = parser.parse_args()

    # O boot toca o banco e isso nao tem nada a ver com e-mail: um Postgres lento
    # cospe um traceback por cima do unico texto que importa aqui.
    #
    # `TESTING` de proposito NAO entra: ele faria o servico de e-mail so logar em
    # vez de enviar, e o `--enviar` diria "enviado" sem ter enviado nada — que e
    # exatamente a mentira que este script existe para desmascarar.
    logging.disable(logging.CRITICAL)
    try:
        app = create_app()
    finally:
        logging.disable(logging.NOTSET)
    cfg = app.config

    host = cfg.get("MAIL_HOST") or ""
    porta = cfg.get("MAIL_PORT")
    usuario = cfg.get("MAIL_USERNAME") or ""
    senha = cfg.get("MAIL_PASSWORD") or ""

    print("=== configuracao ===")
    print(f"MAIL_HOST      : {host or '(vazio) -> A API NAO ENVIA NADA, so loga'}")
    print(f"MAIL_PORT      : {porta}")
    print(f"MAIL_USERNAME  : {usuario or '(vazio)'}")
    print(f"MAIL_PASSWORD  : {_impressao(senha)}")
    print(f"MAIL_USE_TLS   : {cfg.get('MAIL_USE_TLS')}")
    print(f"MAIL_FROM      : {cfg.get('MAIL_FROM')}")
    print(f"MAIL_ASYNC     : {cfg.get('MAIL_ASYNC')}")
    print(f"APP_URL        : {cfg.get('APP_URL')}  (os links dos e-mails saem daqui)")
    print(f"CODIGO MESTRE  : {cfg.get('EMAIL_VERIFICATION_TEST_CODE') or '(desligado)'}")

    if not host:
        print("\nRESULTADO: SEM CANAL. `MAIL_HOST` vazio — nenhum e-mail sai desta instancia.")
        return 1

    print("\n=== conexao ===")
    try:
        with smtplib.SMTP(host, porta, timeout=20) as smtp:
            smtp.ehlo()
            if cfg.get("MAIL_USE_TLS"):
                smtp.starttls()
                smtp.ehlo()
                print("STARTTLS       : ok (a porta sai desta maquina)")
            if usuario and senha:
                smtp.login(usuario, senha)
                print("LOGIN          : ok (o servidor aceitou a credencial)")
            else:
                print("LOGIN          : pulado (sem usuario/senha configurados)")
    except smtplib.SMTPAuthenticationError as erro:
        print(f"LOGIN          : RECUSADO -> {erro}")
        print(
            "\nRESULTADO: CREDENCIAL INVALIDA. Senha de app do Gmail e revogada em silencio."
            "\n  conta Google > Seguranca > Verificacao em duas etapas > Senhas de app."
            "\n  Sao 16 caracteres; o Google mostra com espacos e OS ESPACOS NAO ENTRAM no .env."
        )
        return 1
    except Exception as erro:  # noqa: BLE001
        print(f"CONEXAO        : FALHOU -> {type(erro).__name__}: {erro}")
        print("\nRESULTADO: a porta nao sai desta maquina ou o host esta errado.")
        return 1

    if not args.enviar:
        print("\nRESULTADO: CANAL OK. Passe --enviar <email> para provar a entrega ponta a ponta.")
        return 0

    print("\n=== envio de verdade ===")
    with app.app_context():
        from app.servicos import email as servico_email

        # Sincrono de proposito: em thread o script terminaria antes de saber se
        # o envio deu certo.
        app.config["MAIL_ASYNC"] = False
        servico_email.enviar_codigo_cadastro(
            args.enviar,
            "Teste Finan",
            "0000",
            f"{cfg.get('APP_URL').rstrip('/')}/confirmar-email?token=teste-do-script",
            cfg.get("EMAIL_VERIFICATION_TOKEN_EXPIRES_HOURS"),
            cfg.get("EMAIL_VERIFICATION_MAX_ATTEMPTS"),
        )
    print(f"enviado para {args.enviar} com o codigo 0000 (nao confirma nada, e so o formato)")
    print("Se nao chegar em 2 min: caixa de spam, e depois o painel do Gmail (envios bloqueados).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
