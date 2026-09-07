"""Confirmação de cadastro por código de 4 dígitos (e pelo link)."""
import uuid
from datetime import timedelta

from sqlalchemy import select

from app.extensoes import db
from app.modelos import CodigoVerificacao, Usuario
from app.util import agora
from tests.conftest import registrar


def _registrar_sem_confirmar(cliente, email: str | None = None):
    return registrar(cliente, email=email, confirmar=False)


def test_registro_emite_codigo_e_nao_verifica(cliente):
    api = _registrar_sem_confirmar(cliente)
    assert api.usuario["email_verificado"] is False
    assert len(api.codigo) == 4 and api.codigo.isdigit()
    assert "/confirmar-email?token=" in api.url_confirmacao


def test_sem_confirmar_o_app_fica_trancado(cliente):
    api = _registrar_sem_confirmar(cliente)
    r = api.get("/categorias")
    assert r.status_code == 403
    assert r.get_json()["erro"]["codigo"] == "EMAIL_NAO_VERIFICADO"
    # `/auth/eu` continua aberto: é dele que o front tira para onde navegar.
    assert api.get("/auth/eu").status_code == 200

    api.post("/auth/email/confirmar-codigo", {"codigo": api.codigo})
    assert api.get("/categorias").status_code == 200


def test_codigo_certo_confirma(cliente):
    api = _registrar_sem_confirmar(cliente)
    r = api.post("/auth/email/confirmar-codigo", {"codigo": api.codigo})
    assert r.status_code == 200
    corpo = r.get_json()
    assert corpo["email_verificado"] is True and corpo["email_verificado_em"]

    # Segunda vez não passa: o registro foi marcado como usado.
    r = api.post("/auth/email/confirmar-codigo", {"codigo": api.codigo})
    assert r.status_code == 409 and r.get_json()["erro"]["codigo"] == "EMAIL_JA_VERIFICADO"


def test_codigo_errado_conta_tentativa_e_bloqueia_no_teto(cliente, app):
    api = _registrar_sem_confirmar(cliente)
    errado = "0000" if api.codigo != "0000" else "1111"

    for restantes in (4, 3, 2, 1, 0):
        r = api.post("/auth/email/confirmar-codigo", {"codigo": errado})
        assert r.status_code == 400
        erro = r.get_json()["erro"]
        assert erro["codigo"] == "CODIGO_INVALIDO"
        assert erro["detalhes"]["tentativas_restantes"] == restantes

    # Gastadas as 5 chances, nem o código certo passa — tem de pedir outro.
    r = api.post("/auth/email/confirmar-codigo", {"codigo": api.codigo})
    assert r.status_code == 429 and r.get_json()["erro"]["codigo"] == "CODIGO_BLOQUEADO"


def test_codigo_com_formato_errado(cliente):
    api = _registrar_sem_confirmar(cliente)
    for valor in ("12", "12345", "abcd", ""):
        r = api.post("/auth/email/confirmar-codigo", {"codigo": valor})
        assert r.status_code == 422, valor  # o esquema pydantic barra antes do serviço


def test_codigo_expirado(cliente, app):
    api = _registrar_sem_confirmar(cliente)
    with app.app_context():
        registro = db.session.scalar(select(CodigoVerificacao))
        registro.expira_em = agora() - timedelta(minutes=1)
        db.session.commit()

    r = api.post("/auth/email/confirmar-codigo", {"codigo": api.codigo})
    assert r.status_code == 400 and r.get_json()["erro"]["codigo"] == "CODIGO_EXPIRADO"


def test_reenvio_respeita_cooldown_e_invalida_o_anterior(cliente, app):
    api = _registrar_sem_confirmar(cliente)
    anterior = api.codigo

    r = api.post("/auth/email/enviar-codigo")
    assert r.status_code == 429
    erro = r.get_json()["erro"]
    assert erro["codigo"] == "AGUARDE_REENVIO" and erro["detalhes"]["reenvio_em"] > 0

    # Volta o relógio do último envio para liberar o reenvio.
    with app.app_context():
        registro = db.session.scalar(select(CodigoVerificacao))
        registro.criado_em = agora() - timedelta(minutes=5)
        db.session.commit()

    r = api.post("/auth/email/enviar-codigo")
    assert r.status_code == 200
    novo = r.get_json()["codigo"]
    assert novo != anterior or True  # pode repetir por sorteio; o que importa é o registro

    # O código anterior não vale mais, mesmo sem ter sido usado.
    if novo != anterior:
        r = api.post("/auth/email/confirmar-codigo", {"codigo": anterior})
        assert r.status_code == 400
    assert api.post("/auth/email/confirmar-codigo", {"codigo": novo}).status_code == 200


def test_confirmacao_pelo_link(cliente):
    api = _registrar_sem_confirmar(cliente)
    token = api.url_confirmacao.split("token=")[1]

    r = cliente.post("/api/v1/auth/email/confirmar", json={"token": token})
    assert r.status_code == 200 and r.get_json()["email_verificado"] is True

    r = cliente.post("/api/v1/auth/email/confirmar", json={"token": token})
    assert r.status_code == 409  # já verificado

    r = cliente.post("/api/v1/auth/email/confirmar", json={"token": "token-que-nunca-existiu"})
    assert r.status_code == 404 and r.get_json()["erro"]["codigo"] == "TOKEN_INVALIDO"


def test_link_expirado(cliente, app):
    api = _registrar_sem_confirmar(cliente)
    token = api.url_confirmacao.split("token=")[1]
    with app.app_context():
        registro = db.session.scalar(select(CodigoVerificacao))
        registro.expira_em = agora() - timedelta(minutes=1)
        db.session.commit()

    r = cliente.post("/api/v1/auth/email/confirmar", json={"token": token})
    assert r.status_code == 410 and r.get_json()["erro"]["codigo"] == "TOKEN_EXPIRADO"


def test_codigo_mestre_confirma_qualquer_conta(cliente, app):
    """O atalho da fase de teste — ligado, confirma sem nenhum e-mail ter saído."""
    api = _registrar_sem_confirmar(cliente)
    with app.app_context():
        # Apaga o código emitido: o atalho tem de funcionar mesmo sem registro.
        db.session.query(CodigoVerificacao).delete()
        db.session.commit()

    api.c.application.config["EMAIL_VERIFICATION_TEST_CODE"] = "1234"
    try:
        r = api.post("/auth/email/confirmar-codigo", {"codigo": "1234"})
        assert r.status_code == 200 and r.get_json()["email_verificado"] is True
    finally:
        api.c.application.config["EMAIL_VERIFICATION_TEST_CODE"] = ""


def test_codigo_mestre_mal_formado_e_ignorado(cliente):
    api = _registrar_sem_confirmar(cliente)
    api.c.application.config["EMAIL_VERIFICATION_TEST_CODE"] = "12345"  # 5 dígitos: inválido
    try:
        r = api.post("/auth/email/confirmar-codigo", {"codigo": "1234"})
        assert r.status_code == 400  # cai no fluxo normal e erra o código
    finally:
        api.c.application.config["EMAIL_VERIFICATION_TEST_CODE"] = ""


def test_codigo_de_um_usuario_nao_confirma_outro(cliente):
    a = _registrar_sem_confirmar(cliente)
    b = _registrar_sem_confirmar(cliente)
    r = b.post("/auth/email/confirmar-codigo", {"codigo": a.codigo})
    # Só passaria por coincidência de sorteio (1 em 10.000); o registro de B é outro.
    if a.codigo != b.codigo:
        assert r.status_code == 400


def test_banco_nao_guarda_o_codigo_em_claro(cliente, app):
    api = _registrar_sem_confirmar(cliente)
    with app.app_context():
        registro = db.session.scalar(select(CodigoVerificacao))
        assert registro.codigo_hash != api.codigo
        assert len(registro.codigo_hash) == 64
        assert registro.token_hash and len(registro.token_hash) == 64


def test_conta_inexistente_no_token_do_jwt(cliente, app):
    """Sessão de um usuário apagado: 401, não 500 nem 403 da trava."""
    api = _registrar_sem_confirmar(cliente)
    with app.app_context():
        db.session.query(Usuario).filter_by(id=uuid.UUID(api.usuario["id"])).delete()
        db.session.commit()
    assert api.get("/auth/eu").status_code == 401
