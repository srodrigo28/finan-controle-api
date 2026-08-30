def test_healthz(cliente):
    r = cliente.get("/healthz")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok", "banco": "ok"}


def test_registro_cria_categorias_padrao(api):
    assert api.usuario["email"].endswith("@teste.com")
    cats = api.get("/categorias").get_json()["dados"]
    nomes = {c["nome"] for c in cats}
    assert {"Mercado", "Hortifruti", "Limpeza", "Bebidas", "Moradia", "Salário", "Outros"} <= nomes
    mercado = next(c for c in cats if c["nome"] == "Mercado")
    hortifruti = next(c for c in cats if c["nome"] == "Hortifruti")
    assert hortifruti["pai_id"] == mercado["id"]
    assert mercado["icone"] == "shopping-cart"


def test_registro_email_duplicado(cliente):
    dados = {"nome": "Ana", "email": "ana@teste.com", "senha": "segredo123"}
    assert cliente.post("/api/v1/auth/registrar", json=dados).status_code == 201
    r = cliente.post("/api/v1/auth/registrar", json=dados)
    assert r.status_code == 409
    assert r.get_json()["erro"]["codigo"] == "CONFLITO"


def test_validacao_formato_erro(cliente):
    r = cliente.post("/api/v1/auth/registrar", json={"nome": "A", "email": "x", "senha": "1"})
    assert r.status_code == 422
    erro = r.get_json()["erro"]
    assert erro["codigo"] == "VALIDACAO"
    assert {"nome", "email", "senha"} <= set(erro["detalhes"])


def test_login_refresh_e_eu(cliente):
    cliente.post("/api/v1/auth/registrar", json={"nome": "Ana", "email": "ana@teste.com", "senha": "segredo123"})
    r = cliente.post("/api/v1/auth/login", json={"email": "ANA@teste.com", "senha": "segredo123"})
    assert r.status_code == 200
    tokens = r.get_json()

    r = cliente.post("/api/v1/auth/login", json={"email": "ana@teste.com", "senha": "errada"})
    assert r.status_code == 401

    r = cliente.post("/api/v1/auth/refresh", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert r.status_code == 200 and "access_token" in r.get_json()

    r = cliente.get("/api/v1/auth/eu", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r.get_json()["nome"] == "Ana"

    r = cliente.patch(
        "/api/v1/auth/eu",
        json={"orcamento_mensal": 3000, "orcamento_diario": 100},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.get_json()["orcamento_mensal"] == 3000.0


def test_rota_protegida_sem_token(cliente):
    r = cliente.get("/api/v1/categorias")
    assert r.status_code == 401
    assert r.get_json()["erro"]["codigo"] == "NAO_AUTENTICADO"
