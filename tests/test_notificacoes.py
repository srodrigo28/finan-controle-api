"""Web Push: chave VAPID, inscrição, teste e cron de lembretes (webpush mockado)."""
from datetime import date

ASSINATURA = {"endpoint": "https://push.exemplo/abc", "keys": {"p256dh": "p", "auth": "a"}, "aparelho": "Pixel"}


def test_vapid_publica(cliente):
    r = cliente.get("/api/v1/notificacoes/vapid")
    assert r.status_code == 200 and r.get_json()["chave_publica"].startswith("BF3")


def test_inscrever_e_listar_e_remover(api):
    r = api.post("/notificacoes/inscrever", ASSINATURA)
    assert r.status_code == 201 and r.get_json()["aparelho"] == "Pixel"
    api.post("/notificacoes/inscrever", ASSINATURA)  # idempotente pelo endpoint
    assert len(api.get("/notificacoes/inscricoes").get_json()["dados"]) == 1
    assert api.delete("/notificacoes/inscrever").status_code == 204
    assert api.get("/notificacoes/inscricoes").get_json()["dados"] == []


def test_lembretes_via_cron(api, app, monkeypatch, chave_vapid):
    import app.servicos.notificacoes as mod

    enviados = []
    monkeypatch.setattr(mod, "webpush", lambda **kw: enviados.append(kw["data"]))
    monkeypatch.setitem(app.config, "VAPID_PRIVATE_KEY", chave_vapid)
    api.post("/notificacoes/inscrever", ASSINATURA)
    dia = min(28, date.today().day + 1)
    api.post("/contas", {"nome": "Energia", "valor_estimado": 210.4, "dia_vencimento": dia, "recorrencia": "mensal", "lembrete_dias": 5})

    assert api.c.post("/api/v1/notificacoes/enviar-lembretes").status_code == 401  # sem token
    r = api.c.post("/api/v1/notificacoes/enviar-lembretes", headers={"X-Cron-Token": "cron-teste"})
    assert r.status_code == 200, r.get_json()
    corpo = r.get_json()
    assert corpo["ativo"] is True and corpo["enviados"] >= 1
    assert any("Energia" in e for e in enviados)

    assert api.post("/notificacoes/testar").get_json()["enviados"] == 1


# ---------- E005: configuração ruim do VAPID não pode derrubar o cron ----------


def _usuario_com_conta_vencendo(api):
    api.post("/notificacoes/inscrever", ASSINATURA)
    dia = min(28, date.today().day + 1)
    api.post("/contas", {"nome": "Energia", "valor_estimado": 210.4, "dia_vencimento": dia, "recorrencia": "mensal", "lembrete_dias": 5})


def test_cron_com_chave_vapid_invalida_responde_erro_claro(api, app, monkeypatch, chave_vapid):
    # O caso de produção: a linha seguinte do .env.deploy colada no fim da chave.
    chave_colada = chave_vapid + "VAPID_SUBJECT=mailto:contato@exemplo.com.br"
    monkeypatch.setitem(app.config, "VAPID_PRIVATE_KEY", chave_colada)
    _usuario_com_conta_vencendo(api)
    r = api.c.post("/api/v1/notificacoes/enviar-lembretes", headers={"X-Cron-Token": "cron-teste"})
    assert r.status_code == 503, r.get_json()
    erro = r.get_json()["erro"]
    assert erro["codigo"] == "PUSH_CONFIG_INVALIDA"
    assert "VAPID_PRIVATE_KEY" in erro["mensagem"]
    assert chave_colada not in r.get_data(as_text=True)  # nunca ecoa o segredo


def test_vapid_subject_vazio_usa_o_padrao(api, app, monkeypatch, chave_vapid):
    import app.servicos.notificacoes as mod

    claims = []
    monkeypatch.setattr(mod, "webpush", lambda **kw: claims.append(kw["vapid_claims"]))
    monkeypatch.setitem(app.config, "VAPID_PRIVATE_KEY", chave_vapid)
    monkeypatch.setitem(app.config, "VAPID_SUBJECT", "")
    api.post("/notificacoes/inscrever", ASSINATURA)
    assert api.post("/notificacoes/testar").get_json()["enviados"] == 1
    assert claims and claims[0]["sub"].startswith("mailto:")


def test_falha_inesperada_numa_inscricao_nao_derruba_o_cron(api, app, monkeypatch, chave_vapid):
    import app.servicos.notificacoes as mod
    from app.extensoes import db
    from app.modelos import InscricaoPush

    def webpush_falso(**kw):
        if kw["subscription_info"]["endpoint"].endswith("/quebrada"):
            raise RuntimeError("falha de rede inesperada")

    monkeypatch.setattr(mod, "webpush", webpush_falso)
    monkeypatch.setitem(app.config, "VAPID_PRIVATE_KEY", chave_vapid)
    _usuario_com_conta_vencendo(api)
    api.post("/notificacoes/inscrever", {**ASSINATURA, "endpoint": "https://push.exemplo/quebrada", "aparelho": "Velho"})

    r = api.c.post("/api/v1/notificacoes/enviar-lembretes", headers={"X-Cron-Token": "cron-teste"})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["enviados"] >= 1  # a inscrição boa recebeu
    with app.app_context():
        quebrada = db.session.query(InscricaoPush).filter(InscricaoPush.endpoint.like("%/quebrada")).one()
        assert quebrada.ultimo_erro and "RuntimeError" in quebrada.ultimo_erro
