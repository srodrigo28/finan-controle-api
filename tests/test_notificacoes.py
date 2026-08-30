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


def test_lembretes_via_cron(api, app, monkeypatch):
    import app.servicos.notificacoes as mod

    enviados = []
    monkeypatch.setattr(mod, "webpush", lambda **kw: enviados.append(kw["data"]))
    monkeypatch.setitem(app.config, "VAPID_PRIVATE_KEY", "priv")
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
