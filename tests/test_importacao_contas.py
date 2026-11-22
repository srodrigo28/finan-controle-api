"""6c: conta de consumo (água, luz…) e boleto lidos pela IA viram conta agendada do mês.

Nenhum teste chama a Anthropic (leitor falso). Datas fixas (E002): a competência vem do vencimento lido.
Decisões do dono (22/11/2026): a pagar → ocorrência do mês; paga → lançamento + baixa; companhia nova →
sugere conta mensal; débito automático sozinho não é pago; pulada volta a pendente; o original fica na
ocorrência e vira anexo do lançamento na baixa.
"""
import io
import logging

import pytest

from app.servicos import leitor_ia
from app.servicos.leitor_ia import ContaLida, Leitura, LinhaLida, ResultadoLeitura
from tests.test_codigo_barras import _arrecadacao

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
CODIGO, LINHA = _arrecadacao(18734, "6")  # luz, R$ 187,34, empresa 0138 → chave "arrec:3:0138"


@pytest.fixture(autouse=True)
def leitor(monkeypatch):
    estado = {"conta": None, "linhas": None, "tipo": "conta_consumo"}

    def falso(conteudo, mime, categorias, hoje):
        conta = estado["conta"]
        linhas = estado["linhas"] if estado["linhas"] is not None else [LinhaLida(
            data=conta.vencimento if conta else "2026-12-10", valor_centavos=(conta.valor_centavos if conta else 18734) or 18734,
            tipo="despesa", descricao="Energia Equatorial", categoria_id=None, forma_pagamento="boleto", confianca="alta",
        )]
        return Leitura(
            resultado=ResultadoLeitura(tipo_documento=estado["tipo"], estabelecimento="Equatorial Energia", linhas=linhas,
                                       observacao=None, conta=conta),
            modelo="claude-sonnet-5-5", tokens_entrada=3000, tokens_saida=300,
        )

    monkeypatch.setattr(leitor_ia, "ler_documento", falso)
    return estado


def _conta_lida(**kw) -> ContaLida:
    base = dict(
        tipo_servico="luz", emissor_nome="Equatorial Energia", emissor_cnpj=None, identificador_cliente="UC 3001234567",
        referencia="2026-11", vencimento="2026-12-10", valor_centavos=18734, linha_digitavel=LINHA,
        consumo=312.0, unidade="kWh", pago=False, data_pagamento=None, evidencia_pago="nenhuma", debito_automatico=False,
    )
    base.update(kw)
    return ContaLida(**base)


_contador = {"n": 0}


def _enviar(api):
    # Cada envio é um arquivo diferente (o mesmo arquivo de novo dá 409 de propósito).
    _contador["n"] += 1
    conteudo = PNG + str(_contador["n"]).encode()
    r = api.c.post("/api/v1/importacoes", data={"arquivo": (io.BytesIO(conteudo), "conta.png", "image/png")},
                   headers=api.cabecalhos, content_type="multipart/form-data")
    assert r.status_code == 202, r.get_json()
    return r.get_json()


def _ocorrencias(api, competencia="2026-12"):
    return api.get(f"/contas/ocorrencias?competencia={competencia}").get_json()["dados"]


# ---------- leitura → rascunho ----------

def test_conta_a_pagar_sem_conta_cadastrada_sugere_conta_mensal(api, leitor):
    leitor["conta"] = _conta_lida()
    imp = _enviar(api)
    assert imp["estado"] == "revisar" and imp["tipo_documento"] == "conta_consumo"
    linha = imp["linhas"][0]
    assert linha["destino"] == "conta" and linha["confianca"] == "alta"
    c = linha["conta"]
    assert c["conta_id"] is None and c["casamento"] is None
    assert c["conta_nova"] == {"nome": "Equatorial Energia", "dia_vencimento": 10}
    assert (c["codigo_valido"], c["linha_digitavel"], c["emissor_chave"]) == (True, LINHA, "arrec:3:0138")
    assert (c["referencia"], c["consumo"], c["unidade"], c["pago"]) == ("2026-11", 312.0, "kWh", False)


def test_confirmar_conta_a_pagar_cria_conta_e_preenche_o_mes_sem_lancamento(api, leitor):
    leitor["conta"] = _conta_lida()
    imp = _enviar(api)
    r = api.post(f"/importacoes/{imp['id']}/confirmar")
    assert r.status_code == 200, r.get_json()
    corpo = r.get_json()
    assert corpo["lancamentos"] == [] and len(corpo["ocorrencias"]) == 1
    assert api.get("/lancamentos").get_json()["total"] == 0

    contas = api.get("/contas").get_json()["dados"]
    assert len(contas) == 1
    conta = contas[0]
    assert (conta["nome"], conta["valor_estimado"], conta["dia_vencimento"], conta["recorrencia"]) == ("Equatorial Energia", 187.34, 10, "mensal")
    assert (conta["emissor_chave"], conta["identificador_cliente"], conta["tipo_servico"]) == ("arrec:3:0138", "UC 3001234567", "luz")

    ocs = _ocorrencias(api)
    assert len(ocs) == 1  # o gerador não duplica o mês preenchido
    oc = ocs[0]
    assert (oc["vencimento"], oc["valor_real"], oc["status"]) == ("2026-12-10", 187.34, "pendente")
    assert (oc["linha_digitavel"], oc["consumo"], oc["unidade_consumo"], oc["referencia"], oc["importacao_id"]) == (
        LINHA, 312.0, "kWh", "2026-11", imp["id"])

    # idempotente: confirmar de novo devolve a mesma ocorrência e não cria outra conta
    de_novo = api.post(f"/importacoes/{imp['id']}/confirmar").get_json()
    assert [o["id"] for o in de_novo["ocorrencias"]] == [oc["id"]]
    assert len(api.get("/contas").get_json()["dados"]) == 1


def test_mes_seguinte_casa_pela_companhia_e_instalacao(api, leitor):
    leitor["conta"] = _conta_lida()
    api.post(f"/importacoes/{_enviar(api)['id']}/confirmar")
    conta_id = api.get("/contas").get_json()["dados"][0]["id"]

    # com o código: casa pela chave da companhia + instalação
    leitor["conta"] = _conta_lida(referencia="2026-12", vencimento="2027-01-12")
    c = _enviar(api)["linhas"][0]["conta"]
    assert (c["conta_id"], c["casamento"]) == (conta_id, "chave_identificador")

    # código ilegível no papel: a instalação sozinha casa
    leitor["conta"] = _conta_lida(referencia="2026-12", vencimento="2027-01-12", valor_centavos=20110, linha_digitavel=None)
    imp = _enviar(api)
    c = imp["linhas"][0]["conta"]
    assert (c["conta_id"], c["casamento"]) == (conta_id, "identificador")
    api.post(f"/importacoes/{imp['id']}/confirmar")
    oc = _ocorrencias(api, "2027-01")[0]  # vencimento em janeiro → competência 2027-01
    assert (oc["vencimento"], oc["valor_real"]) == ("2027-01-12", 201.1)
    assert oc["linha_digitavel"] is None  # sem código lido, nada a copiar


def test_conta_existente_casa_pelo_nome_e_ganha_a_chave(api, leitor):
    existente = api.post("/contas", {"nome": "Energia - Equatorial", "valor_estimado": 150, "dia_vencimento": 8}).get_json()
    leitor["conta"] = _conta_lida()
    imp = _enviar(api)
    c = imp["linhas"][0]["conta"]
    assert (c["conta_id"], c["casamento"]) == (existente["id"], "nome")
    api.post(f"/importacoes/{imp['id']}/confirmar")
    conta = api.get(f"/contas/{existente['id']}").get_json()
    conta = conta.get("conta", conta)
    assert conta["emissor_chave"] == "arrec:3:0138" and conta["valor_estimado"] == 150.0  # estimado não muda
    oc = _ocorrencias(api)[0]
    assert (oc["conta_id"], oc["vencimento"], oc["valor_real"]) == (existente["id"], "2026-12-10", 187.34)


def test_conta_paga_com_conta_cadastrada_vira_lancamento_com_anexo_e_baixa(api, leitor):
    existente = api.post("/contas", {"nome": "Equatorial", "valor_estimado": 150, "dia_vencimento": 10}).get_json()
    leitor["conta"] = _conta_lida(pago=True, evidencia_pago="carimbo", data_pagamento="2026-12-08")
    imp = _enviar(api)
    linha = imp["linhas"][0]
    assert linha["destino"] == "conta" and linha["conta"]["pago"] is True
    corpo = api.post(f"/importacoes/{imp['id']}/confirmar").get_json()
    assert len(corpo["lancamentos"]) == 1
    lanc = corpo["lancamentos"][0]
    assert (lanc["valor"], lanc["data"], lanc["conta_id"], lanc["importacao_id"]) == (187.34, "2026-12-08", existente["id"], imp["id"])
    assert [a["armazenamento"] for a in lanc["anexos"]] == ["importacao"]
    ocs = _ocorrencias(api)
    assert len(ocs) == 1 and ocs[0]["status"] == "paga" and ocs[0]["lancamento_id"] == lanc["id"]


def test_conta_paga_sem_conta_cadastrada_e_so_lancamento(api, leitor):
    leitor["conta"] = _conta_lida(pago=True, evidencia_pago="comprovante", data_pagamento="2026-12-09")
    imp = _enviar(api)
    linha = imp["linhas"][0]
    assert linha["destino"] == "lancamento"
    assert linha["conta"]["conta_nova"] == {"nome": "Equatorial Energia", "dia_vencimento": 10}  # a tela oferece, desmarcado
    corpo = api.post(f"/importacoes/{imp['id']}/confirmar").get_json()
    assert len(corpo["lancamentos"]) == 1 and corpo["ocorrencias"] == []
    assert corpo["lancamentos"][0]["data"] == "2026-12-09"
    assert api.get("/contas").get_json()["dados"] == []


def test_debito_automatico_ou_pago_sem_prova_fica_a_pagar(api, leitor):
    leitor["conta"] = _conta_lida(pago=True, evidencia_pago="nenhuma", debito_automatico=True)
    c = _enviar(api)["linhas"][0]["conta"]
    assert c["pago"] is False and c["debito_automatico"] is True


def test_codigo_que_nao_confere_baixa_a_confianca_e_nao_e_gravado(api, leitor):
    errada = LINHA[:20] + str((int(LINHA[20]) + 1) % 10) + LINHA[21:]
    leitor["conta"] = _conta_lida(linha_digitavel=errada)
    imp = _enviar(api)
    linha = imp["linhas"][0]
    assert linha["conta"]["codigo_valido"] is False and linha["confianca"] == "baixa"
    api.post(f"/importacoes/{imp['id']}/confirmar")
    assert _ocorrencias(api)[0]["linha_digitavel"] is None


def test_valor_do_codigo_diferente_do_lido_baixa_a_confianca(api, leitor):
    leitor["conta"] = _conta_lida(valor_centavos=18834)  # o código diz 187,34
    linha = _enviar(api)["linhas"][0]
    assert linha["conta"]["codigo_valido"] is True and linha["confianca"] == "baixa"


def test_mes_pulado_volta_a_pendente_com_a_conta_lida(api, leitor):
    existente = api.post("/contas", {"nome": "Equatorial", "valor_estimado": 150, "dia_vencimento": 10}).get_json()
    oc = _ocorrencias(api)[0]
    api.patch(f"/contas/ocorrencias/{oc['id']}", {"status": "pulada"})
    leitor["conta"] = _conta_lida()
    imp = _enviar(api)
    assert imp["linhas"][0]["conta"]["conta_id"] == existente["id"]
    api.post(f"/importacoes/{imp['id']}/confirmar")
    oc = _ocorrencias(api)[0]
    assert (oc["status"], oc["valor_real"]) == ("pendente", 187.34)


def test_mes_ja_pago_da_409_e_a_importacao_continua_em_revisao(api, leitor):
    api.post("/contas", {"nome": "Equatorial", "valor_estimado": 150, "dia_vencimento": 10})
    oc = _ocorrencias(api)[0]
    api.post(f"/contas/ocorrencias/{oc['id']}/pagar", {"valor_real": 150, "data": "2026-12-05"})
    leitor["conta"] = _conta_lida()
    imp = _enviar(api)
    r = api.post(f"/importacoes/{imp['id']}/confirmar")
    assert r.status_code == 409 and r.get_json()["erro"]["codigo"] == "OCORRENCIA_PAGA", r.get_json()
    assert r.get_json()["erro"]["detalhes"]["ocorrencia_id"] == oc["id"]
    assert api.get(f"/importacoes/{imp['id']}").get_json()["estado"] == "revisar"
    assert api.get("/lancamentos").get_json()["total"] == 1  # só o pagamento manual


def test_conta_de_outro_usuario_da_404(api, outro_api, leitor):
    alheia = outro_api.post("/contas", {"nome": "Água", "valor_estimado": 80, "dia_vencimento": 5}).get_json()
    leitor["conta"] = _conta_lida()
    imp = _enviar(api)
    linhas = imp["linhas"]
    linhas[0]["conta"]["conta_id"] = alheia["id"]
    r = api.post(f"/importacoes/{imp['id']}/confirmar", {"linhas": linhas})
    assert r.status_code == 404, r.get_json()


def test_usuario_troca_para_so_lancamento(api, leitor):
    leitor["conta"] = _conta_lida()
    imp = _enviar(api)
    linhas = imp["linhas"]
    linhas[0]["destino"] = "lancamento"
    corpo = api.post(f"/importacoes/{imp['id']}/confirmar", {"linhas": linhas}).get_json()
    assert len(corpo["lancamentos"]) == 1 and corpo["ocorrencias"] == []
    assert api.get("/contas").get_json()["dados"] == []


# ---------- o que quebrava junto ----------

def test_pagar_pela_tela_de_contas_anexa_o_original(api, leitor):
    leitor["conta"] = _conta_lida()
    imp = _enviar(api)
    api.post(f"/importacoes/{imp['id']}/confirmar")
    oc = _ocorrencias(api)[0]
    r = api.post(f"/contas/ocorrencias/{oc['id']}/pagar", {"valor_real": 187.34, "data": "2026-12-09"})
    lanc = r.get_json()["lancamento"]
    assert lanc["importacao_id"] == imp["id"] and [a["armazenamento"] for a in lanc["anexos"]] == ["importacao"]


def test_reabrir_mes_importado_mantem_o_valor_lido(api, leitor):
    leitor["conta"] = _conta_lida()
    api.post(f"/importacoes/{_enviar(api)['id']}/confirmar")
    oc = _ocorrencias(api)[0]
    api.post(f"/contas/ocorrencias/{oc['id']}/pagar", {"valor_real": 187.34})
    api.post(f"/contas/ocorrencias/{oc['id']}/reabrir")
    oc = _ocorrencias(api)[0]
    assert (oc["status"], oc["valor_real"]) == ("pendente", 187.34)


def test_mudar_o_dia_da_conta_nao_apaga_o_mes_importado(api, leitor):
    leitor["conta"] = _conta_lida(vencimento="2026-12-10")
    api.post(f"/importacoes/{_enviar(api)['id']}/confirmar")
    conta = api.get("/contas").get_json()["dados"][0]
    assert api.patch(f"/contas/{conta['id']}", {"dia_vencimento": 20}).status_code == 200
    ocs = _ocorrencias(api)
    assert len(ocs) == 1 and (ocs[0]["vencimento"], ocs[0]["valor_real"]) == ("2026-12-10", 187.34)


def test_cupom_continua_igual_com_destino_lancamento(api, leitor):
    leitor["tipo"] = "cupom"
    leitor["conta"] = None
    linha = _enviar(api)["linhas"][0]
    assert linha["destino"] == "lancamento" and linha["conta"] is None


def test_linha_digitavel_nao_vai_para_o_log(api, leitor, caplog):
    caplog.set_level(logging.DEBUG)
    leitor["conta"] = _conta_lida()
    api.post(f"/importacoes/{_enviar(api)['id']}/confirmar")
    assert LINHA not in caplog.text and CODIGO not in caplog.text
