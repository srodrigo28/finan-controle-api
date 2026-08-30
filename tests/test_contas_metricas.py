from datetime import date, timedelta


def _seg(d: date) -> date:
    return d - timedelta(days=d.weekday())


def test_contas_e_ocorrencias(api):
    fixas = api.categoria("Contas fixas")
    r = api.post("/contas", {"nome": "Energia", "valor_estimado": 180, "dia_vencimento": 31, "categoria_id": fixas["id"]})
    assert r.status_code == 201, r.get_json()
    conta = r.get_json()
    api.post("/contas", {"nome": "IPVA", "valor_estimado": 900, "dia_vencimento": 10, "recorrencia": "anual", "mes_referencia": 2})

    r = api.get("/contas/ocorrencias?competencia=2026-02")
    corpo = r.get_json()
    assert {o["conta"]["nome"] for o in corpo["dados"]} == {"Energia", "IPVA"}
    energia = next(o for o in corpo["dados"] if o["conta"]["nome"] == "Energia")
    assert energia["vencimento"] == "2026-02-28"  # dia 31 limitado ao fim do mês
    assert energia["status"] == "atrasada"  # competência passada
    assert corpo["total_pendente"] == 1080.0

    # chamar de novo não duplica
    assert len(api.get("/contas/ocorrencias?competencia=2026-02").get_json()["dados"]) == 2
    assert len(api.get("/contas/ocorrencias?competencia=2026-03").get_json()["dados"]) == 1  # só Energia

    r = api.post(f"/contas/ocorrencias/{energia['id']}/pagar", {"valor_real": 175.4, "data": "2026-02-27"})
    assert r.status_code == 200, r.get_json()
    corpo = r.get_json()
    assert corpo["ocorrencia"]["status"] == "paga" and corpo["ocorrencia"]["valor_real"] == 175.4
    assert corpo["lancamento"]["conta_id"] == conta["id"] and corpo["lancamento"]["categoria_id"] == fixas["id"]
    assert api.post(f"/contas/ocorrencias/{energia['id']}/pagar", {"valor_real": 1}).status_code == 409

    r = api.post(f"/contas/ocorrencias/{energia['id']}/reabrir")
    assert r.get_json()["status"] == "atrasada"
    assert api.get("/lancamentos").get_json()["total"] == 0

    assert api.delete(f"/contas/{conta['id']}").status_code == 204
    assert {c["nome"] for c in api.get("/contas").get_json()["dados"]} == {"IPVA"}


def test_metricas_diario_semanal_mensal(api):
    api.patch("/auth/eu", {"orcamento_mensal": 3000, "orcamento_diario": 100})
    mercado = api.categoria("Mercado")
    lazer = api.categoria("Lazer")
    api.patch(f"/categorias/{lazer['id']}", {"orcamento_mensal": 200})

    hoje = date.today()
    seg = _seg(hoje)
    dias = [seg + timedelta(days=i) for i in range(7)]
    api.post("/lancamentos", {"tipo": "despesa", "valor": 120, "categoria_id": mercado["id"], "data": dias[0].isoformat()})
    api.post("/lancamentos", {"tipo": "despesa", "valor": 80, "categoria_id": lazer["id"], "data": dias[2].isoformat()})
    api.post("/lancamentos", {"tipo": "receita", "valor": 500, "data": dias[0].isoformat()})
    # semana anterior
    api.post("/lancamentos", {"tipo": "despesa", "valor": 100, "categoria_id": mercado["id"], "data": (seg - timedelta(days=3)).isoformat()})

    d = api.get(f"/metricas/diario?data={dias[0].isoformat()}").get_json()
    assert d["total_despesas"] == 120.0 and d["total_receitas"] == 500.0
    assert d["orcamento_diario"] == 100.0 and d["saldo_orcamento"] == -20.0
    assert d["por_categoria"] == [{"categoria_id": mercado["id"], "total": 120.0}]
    assert len(d["lancamentos"]) == 2

    s = api.get(f"/metricas/semanal?inicio={dias[3].isoformat()}").get_json()  # qualquer dia da semana → segunda
    assert s["inicio"] == seg.isoformat() and s["fim"] == dias[6].isoformat()
    assert s["total"] == 200.0 and s["total_anterior"] == 100.0
    assert s["variacao_valor"] == 100.0 and s["variacao_pct"] == 100.0
    assert s["dia_mais_caro"] == dias[0].isoformat()
    assert len(s["por_dia"]) == 7 and s["por_dia"][2]["total"] == 80.0
    assert s["por_categoria"][0] == {"categoria_id": mercado["id"], "total": 120.0, "pct": 60.0}
    assert s["semana_mais_cara_do_mes"] is True

    m = api.get(f"/metricas/mensal?mes={seg.year:04d}-{seg.month:02d}").get_json()
    assert m["mes"] == f"{seg.year:04d}-{seg.month:02d}"
    assert m["total_despesas"] >= 120.0 and m["orcamento_mensal"] == 3000.0
    assert len(m["meses_anteriores"]) == 5
    lz = next(c for c in m["por_categoria"] if c["categoria_id"] == lazer["id"])
    assert lz["orcamento"] == 200.0 and lz["pct_orcamento"] == 40.0
    assert m["contas"] == {"pagas": 0, "pendentes": 0, "total_pendente": 0.0}
    assert m["projecao_fechamento"] >= m["total_despesas"] > 0
    assert all("inicio" in w and "total" in w for w in m["semanas"])


def test_mes_invalido(api):
    r = api.get("/metricas/mensal?mes=2026-13")
    assert r.status_code == 422
