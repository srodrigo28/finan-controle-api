"""Esqueci minha senha: link com token opaco, uso único."""
from datetime import timedelta

from sqlalchemy import select

from app.extensoes import db
from app.modelos import CodigoVerificacao
from app.modelos.verificacao import SENHA
from app.util import agora
from tests.conftest import registrar

NOVA = "novasenha123"


def _pedir_link(cliente, email: str) -> str | None:
    r = cliente.post("/api/v1/auth/senha/esqueci", json={"email": email})
    assert r.status_code == 200
    corpo = r.get_json()
    assert "Se este e-mail tiver uma conta" in corpo["mensagem"]
    return corpo.get("url")


def _token(url: str) -> str:
    return url.split("token=")[1]


def test_email_sem_conta_responde_igual_e_nao_grava_nada(cliente, app):
    corpo = cliente.post("/api/v1/auth/senha/esqueci", json={"email": "ninguem@teste.com"}).get_json()
    # Mesma resposta de um e-mail que existe: contar a diferença entregaria a
    # lista de quem tem conta.
    assert corpo["mensagem"] and "url" not in corpo
    with app.app_context():
        assert db.session.scalar(select(CodigoVerificacao)) is None


def test_fluxo_feliz_troca_a_senha(cliente):
    api = registrar(cliente, email="ana@teste.com")
    url = _pedir_link(cliente, "ana@teste.com")

    r = cliente.post("/api/v1/auth/senha/redefinir", json={"token": _token(url), "senha": NOVA})
    assert r.status_code == 200
    # Já devolve a sessão: quem redefiniu não precisa digitar a senha de novo.
    assert r.get_json()["access_token"] and r.get_json()["usuario"]["email"] == "ana@teste.com"

    assert cliente.post("/api/v1/auth/login", json={"email": "ana@teste.com", "senha": NOVA}).status_code == 200
    antiga = cliente.post("/api/v1/auth/login", json={"email": "ana@teste.com", "senha": "segredo123"})
    assert antiga.status_code == 401
    assert api.usuario["email"] == "ana@teste.com"


def test_email_com_maiusculas_e_espacos_acha_a_conta(cliente):
    registrar(cliente, email="bia@teste.com")
    assert _pedir_link(cliente, "  BIA@teste.com  ") is not None


def test_link_vale_uma_vez_so(cliente):
    registrar(cliente, email="caio@teste.com")
    token = _token(_pedir_link(cliente, "caio@teste.com"))

    assert cliente.post("/api/v1/auth/senha/redefinir", json={"token": token, "senha": NOVA}).status_code == 200
    r = cliente.post("/api/v1/auth/senha/redefinir", json={"token": token, "senha": "outrasenha123"})
    assert r.status_code == 409 and r.get_json()["erro"]["codigo"] == "TOKEN_USADO"


def test_link_expirado(cliente, app):
    registrar(cliente, email="dora@teste.com")
    token = _token(_pedir_link(cliente, "dora@teste.com"))
    with app.app_context():
        registro = db.session.scalar(select(CodigoVerificacao).where(CodigoVerificacao.finalidade == SENHA))
        registro.expira_em = agora() - timedelta(minutes=1)
        db.session.commit()

    r = cliente.post("/api/v1/auth/senha/redefinir", json={"token": token, "senha": NOVA})
    assert r.status_code == 410 and r.get_json()["erro"]["codigo"] == "TOKEN_EXPIRADO"


def test_token_inventado(cliente):
    r = cliente.post("/api/v1/auth/senha/redefinir", json={"token": "nao-existe-este-token", "senha": NOVA})
    assert r.status_code == 404 and r.get_json()["erro"]["codigo"] == "TOKEN_INVALIDO"


def test_senha_curta_e_recusada(cliente):
    registrar(cliente, email="edu@teste.com")
    token = _token(_pedir_link(cliente, "edu@teste.com"))
    r = cliente.post("/api/v1/auth/senha/redefinir", json={"token": token, "senha": "1234567"})
    assert r.status_code == 422 and r.get_json()["erro"]["codigo"] == "VALIDACAO"


def test_segundo_pedido_no_cooldown_nao_emite_novo_link(cliente, app):
    registrar(cliente, email="fabi@teste.com")
    primeiro = _pedir_link(cliente, "fabi@teste.com")
    # Dentro do cooldown a resposta é a mesma, mas nenhum link novo é criado.
    assert _pedir_link(cliente, "fabi@teste.com") is None
    with app.app_context():
        registros = db.session.scalars(
            select(CodigoVerificacao).where(CodigoVerificacao.finalidade == SENHA)
        ).all()
        assert len(registros) == 1
    assert primeiro


def test_novo_link_invalida_o_anterior(cliente, app):
    registrar(cliente, email="gui@teste.com")
    antigo = _token(_pedir_link(cliente, "gui@teste.com"))
    with app.app_context():
        registro = db.session.scalar(select(CodigoVerificacao).where(CodigoVerificacao.finalidade == SENHA))
        registro.criado_em = agora() - timedelta(minutes=5)
        db.session.commit()

    novo = _token(_pedir_link(cliente, "gui@teste.com"))
    r = cliente.post("/api/v1/auth/senha/redefinir", json={"token": antigo, "senha": NOVA})
    assert r.status_code == 409 and r.get_json()["erro"]["codigo"] == "TOKEN_USADO"
    assert cliente.post("/api/v1/auth/senha/redefinir", json={"token": novo, "senha": NOVA}).status_code == 200


def test_redefinir_tambem_confirma_o_email(cliente):
    """Quem redefine a senha provou que lê a caixa de entrada — não fica preso na tela do código."""
    api = registrar(cliente, email="hugo@teste.com", confirmar=False)
    assert api.usuario["email_verificado"] is False

    token = _token(_pedir_link(cliente, "hugo@teste.com"))
    r = cliente.post("/api/v1/auth/senha/redefinir", json={"token": token, "senha": NOVA})
    assert r.status_code == 200 and r.get_json()["usuario"]["email_verificado"] is True


def test_banco_nao_guarda_o_token_em_claro(cliente, app):
    registrar(cliente, email="ivo@teste.com")
    token = _token(_pedir_link(cliente, "ivo@teste.com"))
    with app.app_context():
        registro = db.session.scalar(select(CodigoVerificacao).where(CodigoVerificacao.finalidade == SENHA))
        assert registro.token_hash != token and len(registro.token_hash) == 64
        assert registro.codigo_hash is None  # reset é só link, sem código de 4 dígitos
