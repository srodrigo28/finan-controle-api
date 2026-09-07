"""Envio de e-mail por SMTP — padrão 99dev.

Molde: `d:\\prod\\suwave-app\\project\\app\\api\\app\\services\\email_service.py`.
Ver `docs/prompts/6-setembro-validacao-smtp-esqueci-senha.md`.

Duas regras que vêm de problema real:

* **`MAIL_HOST` vazio não é erro, é o modo dev.** A API loga a mensagem e segue —
  quem roda sem SMTP continua cadastrando e testando.
* **Falha de envio nunca derruba a operação que a disparou**, mas vai para o log
  como `exception`. No SUWAVE a senha de app do Gmail foi revogada em silêncio e
  a API passou semanas sem enviar nada; por isso existe `scripts/checar_smtp.py`,
  que prova o canal sem depender de alguém abrir a caixa de entrada.
"""
import smtplib
import threading
from email.message import EmailMessage

from flask import current_app

ACCENT = "#0e9f6e"
TINTA = "#101418"
CINZA = "#5A6570"


def enviar_codigo_cadastro(email: str, nome: str, codigo: str, url: str, expira_horas: int, tentativas: int) -> None:
    """Código em destaque e link logo abaixo — os dois no mesmo e-mail, de propósito.

    O link resolve para quem abre a mensagem no mesmo aparelho em que se
    cadastrou; o código resolve para quem preencheu o formulário no computador e
    lê o e-mail no celular. Cobrar um só caminho obriga metade das pessoas a
    trocar de aparelho no meio do cadastro.
    """
    primeiro = (nome or "").split(" ")[0] or "tudo bem"
    # O código também vai no ASSUNTO: em muitos celulares a prévia da caixa de
    # entrada já basta, sem precisar abrir a mensagem.
    assunto = f"Seu código Finan: {codigo}"
    texto = (
        f"Ola, {primeiro}.\n\n"
        f"Seu codigo de confirmacao e: {codigo}\n\n"
        "Digite-o na tela de confirmacao para ativar sua conta.\n\n"
        f"Se preferir, confirme por este link: {url}\n\n"
        f"O codigo expira em {expira_horas} horas e vale para {tentativas} tentativas. "
        "Se voce nao criou uma conta no Finan, ignore este e-mail."
    )
    corpo = f"""
        <tr><td style="padding:8px 32px 0 32px;">
          <h1 style="margin:0;font-size:24px;line-height:32px;color:{TINTA};">Confirme sua conta, {primeiro}</h1>
        </td></tr>
        <tr><td style="padding:24px 32px 0 32px;" align="center">
          <div style="display:inline-block;background:#F0FBF6;border:2px dashed {ACCENT};border-radius:12px;padding:18px 28px;">
            <div style="font-size:12px;font-weight:bold;color:{ACCENT};letter-spacing:1px;">SEU CÓDIGO</div>
            <div style="font-family:'Courier New',Courier,monospace;font-size:40px;font-weight:bold;color:{TINTA};
                        letter-spacing:12px;line-height:52px;padding-left:12px;">{codigo}</div>
          </div>
          <p style="margin:14px 0 0 0;font-size:13px;color:#8A93A0;">
            Vale por {expira_horas} horas e {tentativas} tentativas.
          </p>
        </td></tr>
        <tr><td style="padding:24px 32px 0 32px;" align="center">
          <a href="{url}" style="display:inline-block;background:{ACCENT};color:#ffffff;text-decoration:none;
                    font-size:15px;font-weight:bold;padding:14px 28px;border-radius:999px;">Ou confirme por aqui</a>
        </td></tr>"""
    _despachar(email, assunto, texto, _pagina(corpo, "Você recebeu este e-mail porque criou uma conta no Finan."), url)


def enviar_reset_senha(email: str, nome: str, url: str, expira_horas: int) -> None:
    primeiro = (nome or "").split(" ")[0] or "tudo bem"
    assunto = "Redefina sua senha do Finan"
    texto = (
        f"Ola, {primeiro}.\n\n"
        "Recebemos um pedido para redefinir a senha da sua conta Finan.\n\n"
        f"Acesse o link abaixo para criar uma nova senha:\n{url}\n\n"
        f"Este link expira em {expira_horas} horas e so pode ser usado uma vez. "
        "Se voce nao pediu a redefinicao, ignore este e-mail — sua senha continua a mesma."
    )
    corpo = f"""
        <tr><td style="padding:8px 32px 0 32px;">
          <h1 style="margin:0;font-size:24px;line-height:32px;color:{TINTA};">Redefinir senha</h1>
          <p style="margin:14px 0 0 0;font-size:15px;line-height:24px;color:{CINZA};">
            Olá, {primeiro}. Recebemos um pedido para trocar a senha da sua conta Finan.
          </p>
        </td></tr>
        <tr><td style="padding:24px 32px 0 32px;" align="center">
          <a href="{url}" style="display:inline-block;background:{ACCENT};color:#ffffff;text-decoration:none;
                    font-size:15px;font-weight:bold;padding:14px 28px;border-radius:999px;">Criar nova senha</a>
          <p style="margin:14px 0 0 0;font-size:13px;color:#8A93A0;">
            O link expira em {expira_horas} horas e vale uma única vez.
          </p>
        </td></tr>"""
    _despachar(email, assunto, texto, _pagina(corpo, "Se você não pediu a redefinição, ignore este e-mail — a senha continua a mesma."), url)


def _pagina(corpo: str, rodape: str) -> str:
    """Moldura do e-mail: tabela com `style=` embutido, nunca flexbox/grid.

    Cliente de e-mail não é navegador — o Outlook renderiza com o motor do Word, e
    `flex`/`grid` simplesmente não existem lá.
    """
    return f"""\
<html><body style="margin:0;padding:0;background:#f4f6f8;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6f8;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0"
             style="max-width:600px;background:#ffffff;border-radius:12px;overflow:hidden;font-family:Arial,Helvetica,sans-serif;">
        <tr><td style="background:{ACCENT};height:6px;line-height:6px;font-size:0;">&nbsp;</td></tr>
        <tr><td style="padding:28px 32px 0 32px;">
          <div style="font-size:18px;font-weight:bold;color:{TINTA};">Finan</div>
          <div style="font-size:12px;color:#8A93A0;">Controle antes do caixa</div>
        </td></tr>{corpo}
        <tr><td style="background:#FAFBFC;padding:20px 32px;border-top:1px solid #E6E9EF;margin-top:24px;">
          <p style="margin:0;font-size:12px;line-height:20px;color:#8A93A0;">{rodape}</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def _despachar(destino: str, assunto: str, texto: str, html: str | None = None, link: str | None = None) -> None:
    app = current_app._get_current_object()
    if app.config.get("TESTING") or not app.config.get("MAIL_HOST"):
        # Sem canal de e-mail, o link vai para o log: é o único jeito de seguir o
        # fluxo em dev. Só acontece com `MAIL_HOST` vazio — em produção, onde o
        # e-mail sai de verdade, nenhum link é registrado.
        app.logger.info("E-mail não enviado (sem MAIL_HOST) para %s: %s | %s", destino, assunto, link or "-")
        return
    if not app.config.get("MAIL_ASYNC"):
        _entregar(app, destino, assunto, texto, html)
        return
    # Thread daemon: o SMTP tem 20 s de timeout e o cadastro não pode ficar
    # pendurado nele. Nada aqui toca o banco — só config e strings já prontas.
    threading.Thread(target=_entregar, args=(app, destino, assunto, texto, html), daemon=True).start()


def _entregar(app, destino: str, assunto: str, texto: str, html: str | None) -> None:
    with app.app_context():
        try:
            mensagem = EmailMessage()
            mensagem["Subject"] = assunto
            mensagem["From"] = app.config["MAIL_FROM"]
            mensagem["To"] = destino
            # O texto puro vai SEMPRE, e primeiro: é o que aparece em leitor de
            # tela, em cliente antigo e na prévia da caixa de entrada. O HTML é a
            # alternativa rica, não o único corpo.
            mensagem.set_content(texto)
            if html:
                mensagem.add_alternative(html, subtype="html")

            with smtplib.SMTP(app.config["MAIL_HOST"], app.config["MAIL_PORT"], timeout=20) as smtp:
                if app.config["MAIL_USE_TLS"]:
                    smtp.starttls()
                usuario, senha = app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"]
                if usuario and senha:
                    smtp.login(usuario, senha)
                smtp.send_message(mensagem)
            app.logger.info("E-mail enviado para %s: %s", destino, assunto)
        except Exception:  # noqa: BLE001
            # Nunca sobe: o registro já foi gravado e a pessoa tem o botão de
            # reenviar. Mas fica no log — foi o silêncio que escondeu o problema
            # no SUWAVE por semanas.
            app.logger.exception("Falha ao enviar e-mail para %s (%s)", destino, assunto)
