"""CRUD completo de contas agendadas: arquivar, reativar, excluir e editar ocorrência."""
from datetime import date

ASSINATURA = {"endpoint": "https://push.exemplo/xyz", "keys": {"p256dh": "p", "auth": "a"}, "aparelho": "Pixel"}


def _conta(api, nome: str, **extra) -> dict:
    corpo = {"nome": nome, "valor_estimado": 100, "dia_vencimento": 10, **extra}
    r = api.post("/contas", corpo)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


# --- Etapa 1: conta arquivada não aparece, não soma e não notifica ---


def test_conta_arquivada_some_do_mes_e_dos_totais(api):
    _conta(api, "Energia", valor_estimado=180, dia_vencimento=10)
    academia = _conta(api, "Academia", valor_estimado=120, dia_vencimento=5)

    corpo = api.get("/contas/ocorrencias?competencia=2026-12").get_json()
    assert {o["conta"]["nome"] for o in corpo["dados"]} == {"Energia", "Academia"}
    assert corpo["total_pendente"] == 300.0

    assert api.delete(f"/contas/{academia['id']}").status_code == 204  # arquiva

    corpo = api.get("/contas/ocorrencias?competencia=2026-12").get_json()
    assert {o["conta"]["nome"] for o in corpo["dados"]} == {"Energia"}
    assert corpo["total_pendente"] == 180.0
    assert {c["nome"] for c in api.get("/contas").get_json()["dados"]} == {"Energia"}


def test_conta_arquivada_e_reativada_volta_com_o_historico(api):
    conta = _conta(api, "Internet", valor_estimado=99, dia_vencimento=15)
    ocs = api.get("/contas/ocorrencias?competencia=2026-12").get_json()["dados"]
    oc = next(o for o in ocs if o["conta"]["nome"] == "Internet")
    api.post(f"/contas/ocorrencias/{oc['id']}/pagar", {"valor_real": 99, "data": "2026-12-15"})

    api.delete(f"/contas/{conta['id']}")
    assert api.get("/contas/ocorrencias?competencia=2026-12").get_json()["dados"] == []
    # arquivada continua acessível com o filtro
    assert {c["nome"] for c in api.get("/contas?incluir_inativas=1").get_json()["dados"]} == {"Internet"}

    assert api.patch(f"/contas/{conta['id']}", {"ativa": True}).status_code == 200
    corpo = api.get("/contas/ocorrencias?competencia=2026-12").get_json()
    assert [o["status"] for o in corpo["dados"]] == ["paga"]  # a ocorrência paga não foi perdida
    assert corpo["total_pago"] == 99.0


# --- Etapa 3: excluir de verdade ---


def test_excluir_definitivo_apaga_conta_e_preserva_o_lancamento_pago(api):
    conta = _conta(api, "Celular", valor_estimado=60, dia_vencimento=20)
    oc = api.get("/contas/ocorrencias?competencia=2026-12").get_json()["dados"][0]
    lanc = api.post(f"/contas/ocorrencias/{oc['id']}/pagar", {"valor_real": 62.5, "data": "2026-12-20"}).get_json()["lancamento"]

    assert api.delete(f"/contas/{conta['id']}?definitivo=1").status_code == 204

    assert api.get("/contas?incluir_inativas=1").get_json()["dados"] == []
    assert api.get("/contas/ocorrencias?competencia=2026-12").get_json()["dados"] == []
    # o gasto continua na vida financeira do usuário, só sem o vínculo com a conta
    r = api.get(f"/lancamentos/{lanc['id']}")
    assert r.status_code == 200 and r.get_json()["conta_id"] is None
    assert r.get_json()["valor"] == 62.5

    assert api.delete(f"/contas/{conta['id']}?definitivo=1").status_code == 404


def test_excluir_conta_de_outro_usuario_nao_encontra(api, outro_api):
    conta = _conta(api, "Água")
    assert outro_api.delete(f"/contas/{conta['id']}?definitivo=1").status_code == 404
    assert len(api.get("/contas").get_json()["dados"]) == 1


# --- Etapa 5: detalhe e histórico ---


def test_detalhe_traz_resumo_e_historico_ordenado(api):
    conta = _conta(api, "Luz", valor_estimado=200, dia_vencimento=10)
    api.get("/contas/ocorrencias?competencia=2026-11")  # gera novembro
    dez = api.get("/contas/ocorrencias?competencia=2026-12").get_json()["dados"][0]
    api.post(f"/contas/ocorrencias/{dez['id']}/pagar", {"valor_real": 210, "data": "2026-12-10"})

    d = api.get(f"/contas/{conta['id']}").get_json()
    assert d["nome"] == "Luz"
    assert d["resumo"] == {
        "ocorrencias_total": 2,
        "pagas": 1,
        "total_pago": 210.0,
        "media_paga": 210.0,
        "ultimo_pagamento": "2026-12-10",
    }

    historico = api.get(f"/contas/{conta['id']}/ocorrencias?limite=5").get_json()["dados"]
    assert [o["competencia"] for o in historico] == ["2026-12", "2026-11"]  # mais recente primeiro
    assert historico[0]["lancamento_id"] is not None

    assert api.get(f"/contas/{conta['id']}").status_code == 200


def test_detalhe_de_outro_usuario_nao_encontra(api, outro_api):
    conta = _conta(api, "Gás")
    assert outro_api.get(f"/contas/{conta['id']}").status_code == 404
    assert outro_api.get(f"/contas/{conta['id']}/ocorrencias").status_code == 404


# --- Etapa 6: CRUD da ocorrência ---


def test_ajustar_valor_e_vencimento_de_um_mes_so(api):
    _conta(api, "Condomínio", valor_estimado=500, dia_vencimento=5)
    oc = api.get("/contas/ocorrencias?competencia=2026-12").get_json()["dados"][0]

    r = api.patch(f"/contas/ocorrencias/{oc['id']}", {"valor_real": 545.9, "vencimento": "2026-12-18"})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["vencimento"] == "2026-12-18" and r.get_json()["valor_real"] == 545.9

    corpo = api.get("/contas/ocorrencias?competencia=2026-12").get_json()
    assert corpo["total_pendente"] == 545.9  # o mês ajustado manda no total
    # e o mês seguinte segue o valor da conta
    assert api.get("/contas/ocorrencias?competencia=2027-01").get_json()["total_pendente"] == 500.0


def test_pular_mes_sai_do_total_e_do_push_e_volta_ao_desfazer(api, app, monkeypatch):
    import app.servicos.notificacoes as mod

    enviados = []
    monkeypatch.setattr(mod, "webpush", lambda **kw: enviados.append(kw["data"]))
    monkeypatch.setitem(app.config, "VAPID_PRIVATE_KEY", "priv")
    api.post("/notificacoes/inscrever", ASSINATURA)

    dia = min(28, date.today().day + 1)
    _conta(api, "Faculdade", valor_estimado=800, dia_vencimento=dia, lembrete_dias=5)
    hoje_comp = date.today().strftime("%Y-%m")
    oc = api.get(f"/contas/ocorrencias?competencia={hoje_comp}").get_json()["dados"][0]

    assert api.patch(f"/contas/ocorrencias/{oc['id']}", {"status": "pulada"}).get_json()["status"] == "pulada"
    corpo = api.get(f"/contas/ocorrencias?competencia={hoje_comp}").get_json()
    assert corpo["total_pendente"] == 0.0
    assert [o["status"] for o in corpo["dados"]] == ["pulada"]  # continua visível, só não cobra

    r = api.c.post("/api/v1/notificacoes/enviar-lembretes", headers={"X-Cron-Token": "cron-teste"})
    assert r.get_json()["enviados"] == 0 and enviados == []

    api.patch(f"/contas/ocorrencias/{oc['id']}", {"status": "pendente"})
    assert api.get(f"/contas/ocorrencias?competencia={hoje_comp}").get_json()["total_pendente"] == 800.0


def test_ocorrencia_paga_recusa_ajuste_e_exclusao(api):
    _conta(api, "Seguro", valor_estimado=300, dia_vencimento=8)
    oc = api.get("/contas/ocorrencias?competencia=2026-12").get_json()["dados"][0]
    api.post(f"/contas/ocorrencias/{oc['id']}/pagar", {"valor_real": 300, "data": "2026-12-08"})

    assert api.patch(f"/contas/ocorrencias/{oc['id']}", {"valor_real": 10}).status_code == 409
    assert api.delete(f"/contas/ocorrencias/{oc['id']}").status_code == 409

    api.post(f"/contas/ocorrencias/{oc['id']}/reabrir")
    assert api.patch(f"/contas/ocorrencias/{oc['id']}", {"valor_real": 10}).status_code == 200


def test_excluir_ocorrencia_e_de_outro_usuario(api, outro_api):
    _conta(api, "Netflix", valor_estimado=45, dia_vencimento=12)
    oc = api.get("/contas/ocorrencias?competencia=2026-12").get_json()["dados"][0]

    assert outro_api.delete(f"/contas/ocorrencias/{oc['id']}").status_code == 404
    assert outro_api.patch(f"/contas/ocorrencias/{oc['id']}", {"status": "pulada"}).status_code == 404

    assert api.delete(f"/contas/ocorrencias/{oc['id']}").status_code == 204
    # a conta ainda vence em dezembro, então o vencimento é regerado ao abrir o mês
    assert len(api.get("/contas/ocorrencias?competencia=2026-12").get_json()["dados"]) == 1


# --- Etapa 7: editar a conta realinha os vencimentos futuros ---


def test_mudar_dia_realinha_pendentes_e_preserva_pagas(api):
    conta = _conta(api, "Academia", valor_estimado=150, dia_vencimento=10)
    nov = api.get("/contas/ocorrencias?competencia=2026-11").get_json()["dados"][0]
    api.post(f"/contas/ocorrencias/{nov['id']}/pagar", {"valor_real": 150, "data": "2026-11-10"})
    dez = api.get("/contas/ocorrencias?competencia=2026-12").get_json()["dados"][0]
    assert dez["vencimento"] == "2026-12-10"

    assert api.patch(f"/contas/{conta['id']}", {"dia_vencimento": 25}).status_code == 200

    corpo = api.get("/contas/ocorrencias?competencia=2026-12").get_json()
    assert [o["vencimento"] for o in corpo["dados"]] == ["2026-12-25"]  # uma só, na data nova
    # a paga de novembro não foi tocada
    pagas = api.get("/contas/ocorrencias?competencia=2026-11").get_json()["dados"]
    assert [(o["vencimento"], o["status"]) for o in pagas] == [("2026-11-10", "paga")]


def test_mudar_so_o_nome_nao_mexe_nos_vencimentos(api):
    conta = _conta(api, "Água", valor_estimado=90, dia_vencimento=7)
    antes = api.get("/contas/ocorrencias?competencia=2026-12").get_json()["dados"][0]

    api.patch(f"/contas/{conta['id']}", {"nome": "Água e esgoto", "valor_estimado": 95})

    depois = api.get("/contas/ocorrencias?competencia=2026-12").get_json()["dados"][0]
    assert depois["id"] == antes["id"] and depois["vencimento"] == antes["vencimento"]


def test_push_ignora_conta_arquivada(api, app, monkeypatch):
    import app.servicos.notificacoes as mod

    enviados = []
    monkeypatch.setattr(mod, "webpush", lambda **kw: enviados.append(kw["data"]))
    monkeypatch.setitem(app.config, "VAPID_PRIVATE_KEY", "priv")
    api.post("/notificacoes/inscrever", ASSINATURA)

    dia = min(28, date.today().day + 1)
    conta = _conta(api, "Aluguel", valor_estimado=1500, dia_vencimento=dia, lembrete_dias=5)
    api.delete(f"/contas/{conta['id']}")

    r = api.c.post("/api/v1/notificacoes/enviar-lembretes", headers={"X-Cron-Token": "cron-teste"})
    assert r.status_code == 200 and r.get_json()["enviados"] == 0
    assert enviados == []
