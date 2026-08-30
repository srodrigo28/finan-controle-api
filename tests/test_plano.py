"""Teste gratis de 30 dias: campos no usuario e contagem de dias."""
from datetime import datetime, timedelta, timezone


def test_registro_inicia_teste_de_30_dias(cliente):
    r = cliente.post("/api/v1/auth/registrar", json={"nome": "Ana", "email": "ana-plano@exemplo.com.br", "senha": "senha12345"})
    assert r.status_code == 201
    u = r.get_json()["usuario"]
    assert u["plano"] == "teste"
    assert u["teste_ativo"] is True
    assert 29 <= u["dias_restantes_teste"] <= 30
    expira = datetime.fromisoformat(u["teste_expira_em"].replace("Z", "+00:00"))
    assert timedelta(days=29) < expira - datetime.now(timezone.utc) <= timedelta(days=30)


def test_teste_expirado_fica_inativo(cliente, app):
    from app.extensoes import db
    from app.modelos import Usuario

    cliente.post("/api/v1/auth/registrar", json={"nome": "Bia", "email": "bia-plano@exemplo.com.br", "senha": "senha12345"})
    with app.app_context():
        u = db.session.query(Usuario).filter_by(email="bia-plano@exemplo.com.br").one()
        u.teste_expira_em = datetime.now(timezone.utc) - timedelta(days=1)
        db.session.commit()
    r = cliente.post("/api/v1/auth/login", json={"email": "bia-plano@exemplo.com.br", "senha": "senha12345"})
    u = r.get_json()["usuario"]
    assert u["dias_restantes_teste"] == 0 and u["teste_ativo"] is False


def test_plano_completo_nunca_expira(cliente, app):
    from app.extensoes import db
    from app.modelos import Usuario

    cliente.post("/api/v1/auth/registrar", json={"nome": "Caio", "email": "caio-plano@exemplo.com.br", "senha": "senha12345"})
    with app.app_context():
        u = db.session.query(Usuario).filter_by(email="caio-plano@exemplo.com.br").one()
        u.plano = "completo"
        db.session.commit()
    r = cliente.post("/api/v1/auth/login", json={"email": "caio-plano@exemplo.com.br", "senha": "senha12345"})
    u = r.get_json()["usuario"]
    assert u["dias_restantes_teste"] is None and u["teste_ativo"] is True
