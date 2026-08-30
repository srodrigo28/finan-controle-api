import uuid
from datetime import datetime, timedelta, timezone


def test_fluxo_completo_modo_mercado(api):
    mercado = api.categoria("Mercado")
    hortifruti = api.categoria("Hortifruti")

    r = api.post("/sessoes", {"local": "Assaí", "orcamento": 300})
    assert r.status_code == 201, r.get_json()
    sessao = r.get_json()
    assert sessao["status"] == "aberta" and sessao["total_carrinho"] == 0.0

    sid = sessao["id"]
    arroz = api.post(f"/sessoes/{sid}/itens", {"descricao": "Arroz 5kg", "categoria_id": mercado["id"], "valor_unitario": 24.9, "quantidade": 2}).get_json()
    assert arroz["subtotal"] == 49.8
    banana = api.post(f"/sessoes/{sid}/itens", {"descricao": "Banana", "categoria_id": hortifruti["id"], "valor_unitario": 6.5, "quantidade": 1.25}).get_json()
    assert banana["quantidade"] == 1.25 and banana["subtotal"] == 8.13
    extra = api.post(f"/sessoes/{sid}/itens", {"descricao": "Chocolate", "valor_unitario": 10, "quantidade": 1}).get_json()

    # editar e remover
    api.patch(f"/sessoes/{sid}/itens/{arroz['id']}", {"quantidade": 1})
    assert api.delete(f"/sessoes/{sid}/itens/{extra['id']}").status_code == 204

    detalhe = api.get(f"/sessoes/{sid}").get_json()
    assert detalhe["total_carrinho"] == 24.9 + 8.13
    assert [i["removido"] for i in detalhe["itens"]] == [False, False, True]

    # fechar com divergência
    r = api.post(f"/sessoes/{sid}/fechar", {"total_pago": 30, "motivo_divergencia": "promoção", "forma_pagamento": "debito"})
    assert r.status_code == 200, r.get_json()
    corpo = r.get_json()
    assert corpo["sessao"]["status"] == "fechada"
    assert corpo["sessao"]["total_carrinho"] == 33.03 and corpo["sessao"]["total_pago"] == 30.0
    assert corpo["sessao"]["motivo_divergencia"] == "promoção"
    lanc = corpo["lancamento"]
    assert lanc["valor"] == 30.0 and lanc["sessao_id"] == sid and lanc["categoria_id"] == mercado["id"]
    assert lanc["descricao"] == "Mercado — Assaí"

    # lançamento traz os itens como detalhe (sem os removidos)
    r = api.get(f"/lancamentos/{lanc['id']}")
    assert [i["descricao"] for i in r.get_json()["itens"]] == ["Arroz 5kg", "Banana"]

    # não pode adicionar item em sessão fechada
    assert api.post(f"/sessoes/{sid}/itens", {"descricao": "x", "valor_unitario": 1}).status_code == 409
    assert api.post(f"/sessoes/{sid}/fechar", {"total_pago": 1}).status_code == 409

    # histórico de preço
    r = api.get("/precos/ultimo?descricao=ARROZ  5KG")
    assert r.get_json()["valor_unitario"] == 24.9
    assert api.get("/precos/ultimo?descricao=chocolate").get_json() is None  # item removido não entra
    sug = api.get("/precos/sugestoes?q=ba").get_json()["dados"]
    assert sug == [{"descricao": "Banana", "categoria_id": hortifruti["id"], "valor_unitario": 6.5}]

    # listagem
    lista = api.get("/sessoes?status=fechada").get_json()["dados"]
    assert len(lista) == 1 and "itens" not in lista[0]


def test_abrir_com_id_do_cliente_e_idempotente(api):
    sid = str(uuid.uuid4())
    assert api.post("/sessoes", {"id": sid, "local": "Carrefour"}).status_code == 201
    r = api.post("/sessoes", {"id": sid, "local": "Carrefour"})
    assert r.status_code == 200 and r.get_json()["id"] == sid
    iid = str(uuid.uuid4())
    assert api.post(f"/sessoes/{sid}/itens", {"id": iid, "descricao": "Leite", "valor_unitario": 5}).status_code == 201
    assert api.post(f"/sessoes/{sid}/itens", {"id": iid, "descricao": "Leite", "valor_unitario": 5}).status_code == 200
    assert len(api.get(f"/sessoes/{sid}").get_json()["itens"]) == 1


def test_abandonar(api):
    sid = api.post("/sessoes", {}).get_json()["id"]
    assert api.post(f"/sessoes/{sid}/abandonar").status_code == 204
    assert api.get(f"/sessoes/{sid}").get_json()["status"] == "abandonada"


def test_sincronizar_idempotente(api):
    mercado = api.categoria("Mercado")
    sid, i1, i2 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    agora = datetime.now(timezone.utc)
    carga = {
        "sessoes": [{
            "id": sid, "local": "Atacadão", "orcamento": 200, "status": "aberta",
            "aberta_em": (agora - timedelta(minutes=30)).isoformat(),
            "atualizado_em": agora.isoformat(),
            "itens": [
                {"id": i1, "descricao": "Feijão", "categoria_id": mercado["id"], "valor_unitario": 8.9, "quantidade": 2, "atualizado_em": agora.isoformat()},
                {"id": i2, "descricao": "Café", "valor_unitario": 15, "quantidade": 1, "atualizado_em": agora.isoformat()},
            ],
        }]
    }
    r = api.post("/sessoes/sincronizar", carga)
    assert r.status_code == 200, r.get_json()
    s = r.get_json()["sessoes"][0]
    assert s["id"] == sid and len(s["itens"]) == 2 and s["total_carrinho"] == 32.8

    # reenviar a mesma carga não duplica nada
    s = api.post("/sessoes/sincronizar", carga).get_json()["sessoes"][0]
    assert len(s["itens"]) == 2

    # versão mais nova do cliente vence; item removido offline; sessão fechada offline gera lançamento
    depois = agora + timedelta(minutes=5)
    carga["sessoes"][0]["itens"][0]["quantidade"] = 3
    carga["sessoes"][0]["itens"][0]["atualizado_em"] = depois.isoformat()
    carga["sessoes"][0]["itens"][1]["removido"] = True
    carga["sessoes"][0]["itens"][1]["atualizado_em"] = depois.isoformat()
    carga["sessoes"][0]["status"] = "fechada"
    carga["sessoes"][0]["fechada_em"] = depois.isoformat()
    carga["sessoes"][0]["total_pago"] = 26.7
    carga["sessoes"][0]["forma_pagamento"] = "pix"
    s = api.post("/sessoes/sincronizar", carga).get_json()["sessoes"][0]
    assert s["status"] == "fechada" and s["total_carrinho"] == 26.7 and s["total_pago"] == 26.7
    assert s["motivo_divergencia"] is None and s["lancamento_id"]
    assert api.get("/lancamentos").get_json()["total"] == 1

    # sincronizar de novo depois de fechada: idempotente, não gera 2º lançamento
    s2 = api.post("/sessoes/sincronizar", carga).get_json()["sessoes"][0]
    assert s2["lancamento_id"] == s["lancamento_id"]
    assert api.get("/lancamentos").get_json()["total"] == 1


def test_sincronizar_nao_vaza_entre_usuarios(api, outro_api):
    sid = outro_api.post("/sessoes", {}).get_json()["id"]
    r = api.post("/sessoes/sincronizar", {"sessoes": [{"id": sid, "status": "aberta", "itens": []}]})
    assert r.status_code == 403
    assert api.get(f"/sessoes/{sid}").status_code == 404
