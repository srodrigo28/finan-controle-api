"""Código de barras e linha digitável (FEBRABAN): boleto bancário e arrecadação (água, luz, gás, telefone).

Os exemplos são montados à mão a partir das regras (dígitos calculados nos comentários), e cada código
válido também é provado ao contrário: trocar qualquer dígito tem de invalidar.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.servicos import codigo_barras as cb


# ---------- módulos ----------

def test_modulo_10_a_mao():
    # 261533 → da direita: 3×2=6, 3×1=3, 5×2=10→1, 1×1=1, 6×2=12→3, 2×1=2 → 16 → DV 4
    assert cb.modulo10("261533") == 4
    # soma múltipla de 10 → DV 0: "0" → 0
    assert cb.modulo10("0") == 0


def test_modulo_11_arrecadacao_a_mao():
    # 123 → da direita: 3×2 + 2×3 + 1×4 = 16 → resto 5 → 11-5 = 6
    assert cb.modulo11_arrecadacao("123") == 6
    # resto 0 ou 1 → DV 0: "11" → 1×2+1×3 = 5 → resto 5 → 6;  "0" → resto 0 → 0
    assert cb.modulo11_arrecadacao("0") == 0


def test_modulo_11_boleto_a_mao():
    # 123 → 16 → resto 5 → 6;  resultado 0, 10 ou 11 vira 1: "0" → 11-0 = 11 → 1
    assert cb.modulo11_boleto("123") == 6
    assert cb.modulo11_boleto("0") == 1


# ---------- montagem dos exemplos (as regras, não a função testada) ----------

def _arrecadacao(valor_centavos: int, identificador: str = "6") -> tuple[str, str]:
    """Código de 44 + linha de 48 de uma conta de luz fictícia: 8 (arrecadação) · 3 (energia) · identificador."""
    corpo = f"83{identificador}" + f"{valor_centavos:011d}" + "0138" + "1234567890123456789012345"[:29]
    assert len(corpo) == 43
    modulo = cb.modulo10 if identificador in "67" else cb.modulo11_arrecadacao
    dv_geral = modulo(corpo)
    codigo = corpo[:3] + str(dv_geral) + corpo[3:]
    blocos = [codigo[i:i + 11] for i in range(0, 44, 11)]
    linha = "".join(b + str(modulo(b)) for b in blocos)
    return codigo, linha


def _boleto(fator: int, valor_centavos: int) -> tuple[str, str]:
    banco_moeda = "0019"
    livre = "0000001234567890123456" + "17"  # 25 dígitos do campo livre
    livre = livre[:25].ljust(25, "0")
    sem_dv = banco_moeda + f"{fator:04d}{valor_centavos:010d}" + livre
    dv = cb.modulo11_boleto(sem_dv)
    codigo = banco_moeda + str(dv) + sem_dv[4:]
    c1 = codigo[0:4] + codigo[19:24]
    c2 = codigo[24:34]
    c3 = codigo[34:44]
    linha = (c1 + str(cb.modulo10(c1)) + c2 + str(cb.modulo10(c2)) + c3 + str(cb.modulo10(c3))
             + codigo[4] + codigo[5:19])
    return codigo, linha


def _trocar(linha: str, i: int) -> str:
    """Erro de leitura de UM dígito (±1). O padrão FEBRABAN pega sempre esse caso; uma troca 9→0 (−9) pode
    escapar no DV geral do boleto, porque no módulo 11 dele os restos 0 e 1 dão o mesmo DV (1)."""
    d = int(linha[i])
    return linha[:i] + str(d + 1 if d < 9 else d - 1) + linha[i + 1:]


# ---------- arrecadação (conta de consumo) ----------

@pytest.mark.parametrize("identificador", ["6", "8"])
def test_linha_de_conta_de_luz_valida_e_traz_o_valor(identificador):
    codigo, linha = _arrecadacao(18734, identificador)
    for entrada in (linha, codigo, " ".join([linha[:12], linha[12:24], linha[24:36], linha[36:]])):
        lido = cb.analisar(entrada, hoje=date(2026, 11, 22))
        assert lido is not None and lido.valido, entrada
        assert (lido.tipo, lido.codigo_barras, lido.linha_digitavel) == ("arrecadacao", codigo, linha)
        assert lido.valor == Decimal("187.34")
        assert lido.vencimento is None  # arrecadação não traz vencimento no código


def test_identificador_7_ou_9_e_valor_de_referencia_e_nao_dinheiro():
    codigo, linha = _arrecadacao(18734, "7")
    lido = cb.analisar(linha, hoje=date(2026, 11, 22))
    assert lido.valido and lido.valor is None


def test_qualquer_digito_trocado_invalida_a_linha_de_arrecadacao():
    _, linha = _arrecadacao(18734, "6")
    for i in range(len(linha)):
        trocado = _trocar(linha, i)
        lido = cb.analisar(trocado, hoje=date(2026, 11, 22))
        assert lido is None or not lido.valido, i


# ---------- boleto bancário ----------

def test_boleto_valido_traz_valor_e_vencimento_do_ciclo_novo():
    # Fator 1000 = 22/02/2025 (o ciclo recomeçou depois de 9999 = 21/02/2025); fator 1638 = 638 dias depois.
    codigo, linha = _boleto(1000 + 638, 25990)
    lido = cb.analisar(linha, hoje=date(2026, 11, 22))
    assert lido.valido and lido.tipo == "boleto" and lido.codigo_barras == codigo
    assert lido.valor == Decimal("259.90")
    assert lido.vencimento == date(2026, 11, 22)


def test_boleto_fator_zero_nao_tem_vencimento_e_valor_zero_e_nulo():
    _, linha = _boleto(0, 0)
    lido = cb.analisar(linha, hoje=date(2026, 11, 22))
    assert lido.valido and lido.vencimento is None and lido.valor is None


def test_qualquer_digito_trocado_invalida_o_boleto():
    # DV geral ≠ 1 de propósito: no módulo 11 do boleto os restos 0, 1 e 10 dão todos DV 1, então com DV 1
    # um erro de um dígito pode escapar (ponto cego do próprio padrão FEBRABAN). Ver o teste seguinte.
    codigo, linha = _boleto(1638, 25991)
    assert codigo[4] == "9"
    for i in range(len(linha)):
        trocado = _trocar(linha, i)
        lido = cb.analisar(trocado, hoje=date(2026, 11, 22))
        assert lido is None or not lido.valido, i


def test_boleto_com_dv_1_tem_ponto_cego_e_por_isso_o_valor_e_conferido_contra_o_papel():
    """Documenta o limite: o DV não basta; a importação ainda confere o valor do código com o valor lido."""
    codigo, linha = _boleto(1638, 25990)
    assert codigo[4] == "1"
    lidos = [cb.analisar(_trocar(linha, i), hoje=date(2026, 11, 22)) for i in range(len(linha))]
    escapou = [i for i, lido in enumerate(lidos) if lido is not None and lido.valido]
    assert escapou, "se nada escapa, o ponto cego sumiu e este teste pode sair"
    assert all(i >= 32 for i in escapou)  # só no DV geral/fator/valor: os 3 campos têm DV módulo 10 próprio


@pytest.mark.parametrize("entrada", ["", "abc", "123", "8" * 47 + "x", None])
def test_entrada_que_nao_e_codigo_devolve_none(entrada):
    assert cb.analisar(entrada, hoje=date(2026, 11, 22)) is None
