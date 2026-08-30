"""Anexos no Bucket: upload, download por proxy e exclusão (requests mockado)."""
import io
from types import SimpleNamespace

import requests


class _Resp(SimpleNamespace):
    def json(self):
        return self._json


def _configurar(monkeypatch, app):
    # monkeypatch restaura ao fim do teste — o app é compartilhado entre testes
    for chave, valor in (("BUCKET_URL", "https://bucket.teste"), ("BUCKET_DEFAULT", "finan-controle"), ("BUCKET_TOKEN", "abt_teste")):
        monkeypatch.setitem(app.config, chave, valor)


def _cliente_bucket(monkeypatch, app):
    _configurar(monkeypatch, app)
    chamadas = {"post": [], "get": [], "delete": []}

    def post(url, headers=None, data=None, files=None, timeout=None):
        chamadas["post"].append({"url": url, "headers": headers, "data": data})
        return _Resp(status_code=200, text="", _json={"ok": True, "file_id": 123, "url": "https://bucket.teste/files/public/finan-controle/2026/08/x.jpg", "size_bytes": 3, "mime_type": "image/jpeg"})

    def get(url, headers=None, timeout=None):
        chamadas["get"].append(url)
        return _Resp(status_code=200, content=b"JPG", headers={"Content-Type": "image/jpeg"})

    def delete(url, headers=None, timeout=None):
        chamadas["delete"].append(url)
        return _Resp(status_code=200, text="", _json={"ok": True})

    import app.servicos.bucket as mod
    monkeypatch.setattr(mod.requests, "post", post)
    monkeypatch.setattr(mod.requests, "get", get)
    monkeypatch.setattr(mod.requests, "delete", delete)
    return chamadas


def _lancamento(api):
    return api.post("/lancamentos", {"tipo": "despesa", "valor": 10, "descricao": "farmácia", "data": "2026-08-30"}).get_json()


def _enviar(api, lid, nome, mime, conteudo):
    return api.c.post(
        f"/api/v1/lancamentos/{lid}/anexos",
        data={"arquivo": (io.BytesIO(conteudo), nome, mime)},
        headers=api.cabecalhos,
        content_type="multipart/form-data",
    )


def test_upload_vai_para_o_bucket(api, app, monkeypatch):
    chamadas = _cliente_bucket(monkeypatch, app)
    lanc = _lancamento(api)
    r = _enviar(api, lanc["id"], "cupom.jpg", "image/jpeg", b"JPG")
    assert r.status_code == 201, r.get_json()
    anexo = r.get_json()
    assert anexo["armazenamento"] == "bucket"
    assert chamadas["post"][0]["data"]["bucket"] == "finan-controle"
    assert chamadas["post"][0]["data"]["pasta_virtual"].endswith("/comprovantes/2026-08")
    assert chamadas["post"][0]["headers"]["X-API-Token"] == "abt_teste"

    # download passa pela API (proxy) e devolve o binário do bucket
    d = api.get(f"/anexos/{anexo['id']}/arquivo")
    assert d.status_code == 200 and d.data == b"JPG" and d.mimetype == "image/jpeg"
    assert chamadas["get"][0].startswith("https://bucket.teste/files/public/")

    # excluir apaga no bucket (best-effort)
    assert api.delete(f"/anexos/{anexo['id']}").status_code == 204
    assert chamadas["delete"][0].endswith("/api/files/123")


def test_bucket_fora_do_ar_retorna_503(api, app, monkeypatch):
    import app.servicos.bucket as mod

    _configurar(monkeypatch, app)

    def caiu(*a, **k):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(mod.requests, "post", caiu)
    lanc = _lancamento(api)
    r = _enviar(api, lanc["id"], "cupom.jpg", "image/jpeg", b"JPG")
    assert r.status_code == 503 and r.get_json()["erro"]["codigo"] == "ARQUIVOS_INDISPONIVEL"
    assert api.get(f"/lancamentos/{lanc['id']}").get_json()["anexos"] == []


def test_sem_bucket_configurado_usa_disco(api):
    lanc = _lancamento(api)
    r = _enviar(api, lanc["id"], "boleto.pdf", "application/pdf", b"%PDF")
    assert r.status_code == 201 and r.get_json()["armazenamento"] == "disco"
    assert api.get(f"/anexos/{r.get_json()['id']}/arquivo").data == b"%PDF"
