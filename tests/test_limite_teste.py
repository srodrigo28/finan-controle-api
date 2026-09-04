"""Depois do dia 31: trava criar coisa nova, nunca o que o usuário já registrou."""
from datetime import datetime, timedelta, timezone

from app.extensoes import db
from app.modelos import Usuario


def _expirar(app, api):
    """Empurra o fim do teste para ontem."""
    with app.app_context():
        u = db.session.get(Usuario, __import__("uuid").UUID(api.usuario["id"]))
        u.teste_expira_em = datetime.now(timezone.utc) - timedelta(days=1)
        db.session.commit()


def test_teste_ativo_nao_bloqueia_nada(api):
    assert api.post("/lancamentos", {"tipo": "despesa", "valor": 10, "data": "2026-09-04"}).status_code == 201
    assert api.post("/categorias", {"nome": "Pets", "cor": "#ff0000"}).status_code == 201
    assert api.post("/contas", {"nome": "Luz", "valor_estimado": 90, "dia_vencimento": 10}).status_code == 201
    assert api.post("/sessoes", {"local": "Atacadão"}).status_code == 201


def test_expirado_bloqueia_criacao_com_402(api, app):
    _expirar(app, api)

    for rota, corpo in [
        ("/lancamentos", {"tipo": "despesa", "valor": 10, "data": "2026-09-04"}),
        ("/categorias", {"nome": "Pets", "cor": "#ff0000"}),
        ("/contas", {"nome": "Luz", "valor_estimado": 90, "dia_vencimento": 10}),
        ("/sessoes", {"local": "Atacadão"}),
    ]:
        r = api.post(rota, corpo)
        assert r.status_code == 402, f"{rota} devia recusar: {r.get_json()}"
        assert r.get_json()["erro"]["codigo"] == "TESTE_EXPIRADO"


def test_expirado_continua_lendo_editando_e_exportando(api, app):
    lanc = api.post("/lancamentos", {"tipo": "despesa", "valor": 40, "data": "2026-09-04"}).get_json()
    conta = api.post("/contas", {"nome": "Água", "valor_estimado": 70, "dia_vencimento": 5}).get_json()
    _expirar(app, api)

    assert api.get("/lancamentos").status_code == 200
    assert api.get(f"/lancamentos/{lanc['id']}").status_code == 200
    assert api.get("/metricas/mensal?mes=2026-09").status_code == 200
    assert api.get("/exportar/lancamentos.csv").status_code == 200

    assert api.patch(f"/lancamentos/{lanc['id']}", {"valor": 45}).status_code == 200
    assert api.patch(f"/contas/{conta['id']}", {"nome": "Água e esgoto"}).status_code == 200
    assert api.delete(f"/lancamentos/{lanc['id']}").status_code == 204
    assert api.delete(f"/contas/{conta['id']}").status_code == 204


def test_expirado_ainda_sincroniza_o_carrinho_offline(api, app):
    """Compra feita offline antes de vencer não pode ficar presa no aparelho."""
    sessao = api.post("/sessoes", {"local": "Feira"}).get_json()
    _expirar(app, api)

    # reenvio da mesma sessão (idempotente) continua respondendo 200
    r = api.post("/sessoes", {"id": sessao["id"], "local": "Feira"})
    assert r.status_code == 200 and r.get_json()["id"] == sessao["id"]

    # e os itens do carrinho que já existia continuam entrando
    assert api.post(f"/sessoes/{sessao['id']}/itens", {"descricao": "Arroz", "valor_unitario": 24.9, "quantidade": 1}).status_code == 201
    r = api.post(f"/sessoes/{sessao['id']}/fechar", {"total_pago": 24.9})
    assert r.status_code == 200, r.get_json()
    # a compra virou lançamento normalmente, mesmo com o teste vencido
    assert r.get_json()["lancamento"]["valor"] == 24.9
