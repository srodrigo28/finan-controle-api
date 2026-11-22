"""6d: "parece já lançado" — o mesmo gasto lançado à mão (ou no Modo Mercado) e depois importado.

Regra (meta Q6 de docs/produto/concorrencia-leitura-documentos.md):
- mesmo tipo, valor e dia → a linha vem DESMARCADA, com o lançamento parecido;
- mesmo tipo e valor com até 3 dias de diferença → só o aviso (continua marcada).
Datas fixas (E002).
"""
import io

import pytest

from app.servicos import leitor_ia
from app.servicos.leitor_ia import Leitura, LinhaLida, ResultadoLeitura

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
_n = {"i": 0}


@pytest.fixture(autouse=True)
def leitor(monkeypatch):
    estado = {"linhas": []}

    def falso(conteudo, mime, categorias, hoje):
        return Leitura(
            resultado=ResultadoLeitura(tipo_documento="fatura_cartao", estabelecimento="Banco", linhas=estado["linhas"],
                                       observacao=None, conta=None),
            modelo="claude-sonnet-5-5", tokens_entrada=3000, tokens_saida=300,
        )

    monkeypatch.setattr(leitor_ia, "ler_documento", falso)
    return estado


def _linha(data="2026-11-18", centavos=7362, tipo="despesa", descricao="Mercado Bom Preço") -> LinhaLida:
    return LinhaLida(data=data, valor_centavos=centavos, tipo=tipo, descricao=descricao, categoria_id=None,
                     forma_pagamento="credito", confianca="alta")


def _enviar(api):
    _n["i"] += 1
    r = api.c.post("/api/v1/importacoes", data={"arquivo": (io.BytesIO(PNG + str(_n["i"]).encode()), "f.png", "image/png")},
                   headers=api.cabecalhos, content_type="multipart/form-data")
    assert r.status_code == 202, r.get_json()
    return r.get_json()


def _lancar(api, valor, data, descricao="Mercado", tipo="despesa"):
    r = api.post("/lancamentos", {"tipo": tipo, "valor": valor, "data": data, "descricao": descricao})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def test_mesmo_valor_e_dia_vem_desmarcada_com_o_parecido(api, leitor):
    ja = _lancar(api, 73.62, "2026-11-18", "Mercado (Modo Mercado)")
    leitor["linhas"] = [_linha(), _linha(centavos=1500, descricao="Padaria")]
    linhas = _enviar(api)["linhas"]
    assert linhas[0]["incluir"] is False
    assert linhas[0]["parece_lancado"] == {"lancamento_id": ja["id"], "data": "2026-11-18", "descricao": "Mercado (Modo Mercado)", "forte": True}
    assert linhas[1]["incluir"] is True and linhas[1]["parece_lancado"] is None


def test_ate_3_dias_de_diferenca_so_avisa(api, leitor):
    ja = _lancar(api, 73.62, "2026-11-15")
    leitor["linhas"] = [_linha(data="2026-11-18")]
    linha = _enviar(api)["linhas"][0]
    assert linha["incluir"] is True
    assert linha["parece_lancado"]["lancamento_id"] == ja["id"] and linha["parece_lancado"]["forte"] is False


def test_4_dias_ou_valor_ou_tipo_diferente_nao_avisa(api, leitor):
    _lancar(api, 73.62, "2026-11-14")            # 4 dias antes
    _lancar(api, 73.63, "2026-11-18")            # um centavo a mais
    _lancar(api, 73.62, "2026-11-18", tipo="receita")
    leitor["linhas"] = [_linha()]
    linha = _enviar(api)["linhas"][0]
    assert linha["incluir"] is True and linha["parece_lancado"] is None


def test_um_lancamento_so_casa_com_uma_linha(api, leitor):
    """Duas compras iguais no mesmo dia na fatura e só uma lançada à mão: só uma linha é desmarcada."""
    _lancar(api, 10, "2026-11-18", "Café")
    leitor["linhas"] = [_linha(centavos=1000, descricao="Café"), _linha(centavos=1000, descricao="Café")]
    linhas = _enviar(api)["linhas"]
    assert [l["incluir"] for l in linhas] == [False, True]


def test_lancamento_de_outro_usuario_nao_conta(api, outro_api, leitor):
    _lancar(outro_api, 73.62, "2026-11-18")
    leitor["linhas"] = [_linha()]
    linha = _enviar(api)["linhas"][0]
    assert linha["incluir"] is True and linha["parece_lancado"] is None


def test_lancamento_que_veio_desta_mesma_importacao_nao_conta(api, leitor):
    """Ler de novo não pode acusar os próprios lançamentos como duplicados: compara só com os de fora."""
    leitor["linhas"] = [_linha()]
    imp = _enviar(api)
    api.post(f"/importacoes/{imp['id']}/confirmar")
    leitor["linhas"] = [_linha(centavos=5000)]
    linha = _enviar(api)["linhas"][0]  # outro documento, outro valor
    assert linha["parece_lancado"] is None


def test_confirmar_aceita_a_linha_remarcada_pelo_usuario(api, leitor):
    _lancar(api, 73.62, "2026-11-18")
    leitor["linhas"] = [_linha()]
    imp = _enviar(api)
    linhas = imp["linhas"]
    linhas[0]["incluir"] = True  # "não é o mesmo, salva assim mesmo"
    corpo = api.post(f"/importacoes/{imp['id']}/confirmar", {"linhas": linhas}).get_json()
    assert len(corpo["lancamentos"]) == 1
    assert api.get("/lancamentos").get_json()["total"] == 2
