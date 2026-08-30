"""Documentação Swagger na raiz e spec OpenAPI válido."""


def test_raiz_serve_swagger(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert b"swagger-ui" in r.data and b'url: "openapi.json"' in r.data


def test_docs_alias(cliente):
    assert cliente.get("/docs").status_code == 200


def test_openapi_json(cliente):
    r = cliente.get("/openapi.json")
    assert r.status_code == 200
    spec = r.get_json()
    assert spec["openapi"].startswith("3.1")
    assert "/healthz" in spec["paths"]
    assert "/api/v1/sessoes/sincronizar" in spec["paths"]
    assert "Sincronizar" in spec["components"]["schemas"]
    assert spec["servers"] == [{"url": "/"}]


def test_openapi_respeita_prefixo_da_vps(cliente):
    r = cliente.get("/finan-controle-api/openapi.json", headers={"X-Script-Name": "/finan-controle-api"})
    assert r.status_code == 200
    assert r.get_json()["servers"] == [{"url": "/finan-controle-api"}]
