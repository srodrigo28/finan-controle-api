import uuid


def test_crud_categoria(api):
    cid = str(uuid.uuid4())
    r = api.post("/categorias", {"id": cid, "nome": "Pets", "cor": "#FF00AA", "icone": "dog", "orcamento_mensal": 150})
    assert r.status_code == 201, r.get_json()
    cat = r.get_json()
    assert cat["id"] == cid and cat["orcamento_mensal"] == 150.0

    r = api.patch(f"/categorias/{cid}", {"nome": "Animais", "arquivada": False})
    assert r.get_json()["nome"] == "Animais"

    # subcategoria
    r = api.post("/categorias", {"nome": "Ração", "pai_id": cid})
    assert r.status_code == 201
    sub_id = r.get_json()["id"]
    # não permite 2 níveis
    r = api.post("/categorias", {"nome": "Neto", "pai_id": sub_id})
    assert r.status_code == 422

    # arquivar (DELETE) some da lista padrão, aparece com incluir_arquivadas
    assert api.delete(f"/categorias/{cid}").status_code == 204
    nomes = {c["nome"] for c in api.get("/categorias").get_json()["dados"]}
    assert "Animais" not in nomes and "Ração" not in nomes
    nomes = {c["nome"] for c in api.get("/categorias?incluir_arquivadas=1").get_json()["dados"]}
    assert "Animais" in nomes


def test_reordenar(api):
    cats = api.get("/categorias").get_json()["dados"]
    ids = [c["id"] for c in cats]
    ids.reverse()
    assert api.post("/categorias/reordenar", {"ids": ids}).status_code == 204
    novos = [c["id"] for c in api.get("/categorias").get_json()["dados"]]
    assert novos == ids


def test_categoria_de_outro_usuario_nao_acessivel(api, outro_api):
    cat = outro_api.categoria("Lazer")
    assert api.patch(f"/categorias/{cat['id']}", {"nome": "hack"}).status_code == 404
    assert api.delete(f"/categorias/{cat['id']}").status_code == 404
    r = api.post("/lancamentos", {"tipo": "despesa", "valor": 10, "data": "2026-08-01", "categoria_id": cat["id"]})
    assert r.status_code == 422
