"""Fixtures: app de teste com Postgres real, cliente autenticado e helpers."""
import os
import shutil
import uuid

import pytest
from sqlalchemy import text

from app import create_app
from app.config import ConfigTeste
from app.extensoes import db


@pytest.fixture(scope="session")
def app():
    aplicacao = create_app(ConfigTeste)
    with aplicacao.app_context():
        db.drop_all()
        db.create_all()
        yield aplicacao
        db.session.remove()
        db.drop_all()
    shutil.rmtree(ConfigTeste.UPLOAD_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def limpar_banco(app):
    """Trunca todas as tabelas entre testes (mais rápido que recriar)."""
    yield
    db.session.rollback()
    tabelas = ", ".join(f'"{t.name}"' for t in db.metadata.sorted_tables)
    db.session.execute(text(f"TRUNCATE TABLE {tabelas} RESTART IDENTITY CASCADE"))
    db.session.commit()


@pytest.fixture
def cliente(app):
    return app.test_client()


class Api:
    """Cliente autenticado com açúcar sintático."""

    def __init__(self, cliente, token: str, usuario: dict):
        self.c = cliente
        self.token = token
        self.usuario = usuario
        self.cabecalhos = {"Authorization": f"Bearer {token}"}

    def get(self, rota, **kw):
        return self.c.get(f"/api/v1{rota}", headers=self.cabecalhos, **kw)

    def post(self, rota, json=None, **kw):
        return self.c.post(f"/api/v1{rota}", json=json, headers=self.cabecalhos, **kw)

    def patch(self, rota, json=None, **kw):
        return self.c.patch(f"/api/v1{rota}", json=json, headers=self.cabecalhos, **kw)

    def delete(self, rota, **kw):
        return self.c.delete(f"/api/v1{rota}", headers=self.cabecalhos, **kw)

    def categoria(self, nome: str) -> dict:
        cats = self.get("/categorias").get_json()["dados"]
        return next(c for c in cats if c["nome"] == nome)


def registrar(cliente, email: str | None = None, nome: str = "Teste") -> Api:
    email = email or f"{uuid.uuid4().hex[:8]}@teste.com"
    r = cliente.post("/api/v1/auth/registrar", json={"nome": nome, "email": email, "senha": "segredo123"})
    assert r.status_code == 201, r.get_json()
    corpo = r.get_json()
    return Api(cliente, corpo["access_token"], corpo["usuario"])


@pytest.fixture
def api(cliente) -> Api:
    return registrar(cliente)


@pytest.fixture
def outro_api(cliente) -> Api:
    return registrar(cliente, nome="Outro")
