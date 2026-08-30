import io


def test_criar_listar_editar_excluir(api):
    lazer = api.categoria("Lazer")
    r = api.post("/lancamentos", {
        "tipo": "despesa", "valor": 45.9, "categoria_id": lazer["id"],
        "descricao": "Cinema", "data": "2026-08-10", "forma_pagamento": "pix",
    })
    assert r.status_code == 201, r.get_json()
    lanc = r.get_json()
    assert lanc["valor"] == 45.9 and lanc["forma_pagamento"] == "pix" and lanc["anexos"] == []

    api.post("/lancamentos", {"tipo": "receita", "valor": 3000, "descricao": "Salário", "data": "2026-08-05"})

    r = api.get("/lancamentos?de=2026-08-01&ate=2026-08-31")
    corpo = r.get_json()
    assert corpo["total"] == 2 and corpo["dados"][0]["descricao"] == "Cinema"  # ordenado por data desc

    assert api.get("/lancamentos?tipo=receita").get_json()["total"] == 1
    assert api.get("/lancamentos?busca=cine").get_json()["total"] == 1

    r = api.patch(f"/lancamentos/{lanc['id']}", {"valor": 50})
    assert r.get_json()["valor"] == 50.0

    assert api.delete(f"/lancamentos/{lanc['id']}").status_code == 204
    assert api.get(f"/lancamentos/{lanc['id']}").status_code == 404


def test_valor_deve_ser_positivo(api):
    r = api.post("/lancamentos", {"tipo": "despesa", "valor": 0, "data": "2026-08-10"})
    assert r.status_code == 422


def test_anexo_upload_download_exclusao(api):
    lanc = api.post("/lancamentos", {"tipo": "despesa", "valor": 10, "data": "2026-08-10"}).get_json()

    dados = {"arquivo": (io.BytesIO(b"%PDF-1.4 conteudo"), "nota.pdf", "application/pdf")}
    r = api.post(f"/lancamentos/{lanc['id']}/anexos", data=dados, content_type="multipart/form-data")
    assert r.status_code == 201, r.get_json()
    anexo = r.get_json()
    assert anexo["tipo_mime"] == "application/pdf" and anexo["tamanho"] == 17

    r = api.get(f"/anexos/{anexo['id']}/arquivo")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")

    assert api.get(f"/lancamentos/{lanc['id']}").get_json()["anexos"][0]["id"] == anexo["id"]

    dados = {"arquivo": (io.BytesIO(b"texto"), "x.txt", "text/plain")}
    r = api.post(f"/lancamentos/{lanc['id']}/anexos", data=dados, content_type="multipart/form-data")
    assert r.status_code == 422

    assert api.delete(f"/anexos/{anexo['id']}").status_code == 204
    assert api.get(f"/anexos/{anexo['id']}/arquivo").status_code == 404


def test_isolamento_entre_usuarios(api, outro_api):
    lanc = outro_api.post("/lancamentos", {"tipo": "despesa", "valor": 10, "data": "2026-08-10"}).get_json()
    assert api.get(f"/lancamentos/{lanc['id']}").status_code == 404
    assert api.get("/lancamentos").get_json()["total"] == 0


def test_exportacao(api):
    api.post("/lancamentos", {"tipo": "despesa", "valor": 12.5, "descricao": "Pão", "data": "2026-08-10"})
    r = api.get("/exportar/lancamentos.csv")
    assert r.status_code == 200
    texto = r.data.decode("utf-8-sig")
    assert texto.splitlines()[0] == "data;tipo;valor;categoria;descricao;forma_pagamento;id"
    assert "2026-08-10;despesa;12,50;;Pão" in texto
    r = api.get("/exportar/lancamentos.json")
    assert r.get_json()["total"] == 1
