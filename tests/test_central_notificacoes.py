"""Central de notificações: fila com identidade, marcar lida e fechar sozinha quando resolve."""
from datetime import date, timedelta


def _conta_atrasada(api, nome="Energia", valor=180):
    """Conta vencida no mês corrente — vira aviso de atraso na fila."""
    ontem = date.today() - timedelta(days=1)
    dia = max(1, min(ontem.day, 28))
    return api.post("/contas", {"nome": nome, "valor_estimado": valor, "dia_vencimento": dia}).get_json()


def _fila(api):
    r = api.get("/notificacoes")
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_fila_vazia_para_conta_nova(api):
    corpo = _fila(api)
    assert corpo["nao_lidas"] == len([n for n in corpo["dados"] if not n["lida"]])


def test_conta_atrasada_entra_na_fila_e_nao_duplica(api):
    _conta_atrasada(api)
    api.get(f"/contas/ocorrencias?competencia={date.today():%Y-%m}")  # gera a ocorrência

    primeira = _fila(api)
    avisos = [n for n in primeira["dados"] if n["tipo"].startswith("conta")]
    assert avisos, f"esperava aviso de conta: {primeira['dados']}"
    assert primeira["nao_lidas"] >= 1

    # sincronizar de novo não cria linha nova — é o que a chave garante
    segunda = _fila(api)
    assert len(segunda["dados"]) == len(primeira["dados"])
    assert {n["id"] for n in segunda["dados"]} == {n["id"] for n in primeira["dados"]}


def test_marcar_lida_zera_o_contador_e_persiste(api):
    _conta_atrasada(api)
    api.get(f"/contas/ocorrencias?competencia={date.today():%Y-%m}")
    fila = _fila(api)
    assert fila["nao_lidas"] >= 1

    for n in fila["dados"]:
        assert api.post(f"/notificacoes/{n['id']}/ler").status_code == 200

    depois = _fila(api)
    assert depois["nao_lidas"] == 0
    assert all(n["lida"] for n in depois["dados"])  # continuam na fila, só não contam mais


def test_ler_todas(api):
    _conta_atrasada(api, "Água", 90)
    _conta_atrasada(api, "Internet", 120)
    api.get(f"/contas/ocorrencias?competencia={date.today():%Y-%m}")
    assert _fila(api)["nao_lidas"] >= 1

    r = api.post("/notificacoes/ler-todas")
    assert r.status_code == 200 and r.get_json()["nao_lidas"] == 0
    assert _fila(api)["nao_lidas"] == 0


def test_aviso_sai_da_fila_quando_o_problema_se_resolve(api):
    """Pagou a conta atrasada: o sino para de cobrar sozinho, sem a pessoa marcar nada."""
    _conta_atrasada(api)
    comp = f"{date.today():%Y-%m}"
    ocorrencias = api.get(f"/contas/ocorrencias?competencia={comp}").get_json()["dados"]
    atrasada = next(o for o in ocorrencias if o["status"] == "atrasada")

    antes = [n for n in _fila(api)["dados"] if n["tipo"].startswith("conta")]
    assert antes

    api.post(f"/contas/ocorrencias/{atrasada['id']}/pagar", {"valor_real": 180})

    depois = [n for n in _fila(api)["dados"] if n["tipo"] == antes[0]["tipo"]]
    assert depois == [], f"o aviso devia ter saído da fila: {depois}"


def test_notificacao_de_outro_usuario_nao_encontra(api, outro_api):
    _conta_atrasada(api)
    api.get(f"/contas/ocorrencias?competencia={date.today():%Y-%m}")
    n = _fila(api)["dados"][0]
    assert outro_api.post(f"/notificacoes/{n['id']}/ler").status_code == 404
