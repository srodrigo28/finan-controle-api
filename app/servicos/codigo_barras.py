"""Código de barras e linha digitável brasileiros (padrão FEBRABAN), conferidos pelo dígito verificador.

Dois formatos:
- **arrecadação** (água, luz, gás, telefone, tributos): começa com 8; 44 dígitos no código, 48 na linha
  (4 blocos de 11 + 1 DV). O 3º dígito diz o módulo (6/7 → 10; 8/9 → 11) e se o valor é dinheiro (6/8)
  ou referência (7/9). Não traz vencimento.
- **boleto bancário**: 44 no código, 47 na linha (3 campos com DV módulo 10 + DV geral módulo 11 +
  fator de vencimento e valor).

A IA lê os dígitos e pode errar um: o DV pega. Valor e vencimento do código servem para conferir o que a
IA leu do papel (meta Q1 do docs/produto/concorrencia-leitura-documentos.md: nenhum erro silencioso).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

_PERMITIDO = re.compile(r"^[\d\s.\-]+$")
# O fator de vencimento passou de 9999 (21/02/2025) e recomeçou em 1000 (22/02/2025).
_BASE_ANTIGA = date(1997, 10, 7)
_BASE_NOVA = date(2025, 2, 22)


@dataclass(frozen=True)
class CodigoLido:
    tipo: Literal["arrecadacao", "boleto"]
    codigo_barras: str        # 44 dígitos
    linha_digitavel: str      # 48 (arrecadação) ou 47 (boleto), sem separadores
    valido: bool
    valor: Decimal | None     # None quando o código não traz dinheiro (zero ou valor de referência)
    vencimento: date | None   # só boleto com fator ≠ 0


def modulo10(numero: str) -> int:
    soma = 0
    peso = 2
    for d in reversed(numero):
        p = int(d) * peso
        soma += p // 10 + p % 10
        peso = 1 if peso == 2 else 2
    return (10 - soma % 10) % 10


def _soma11(numero: str) -> int:
    soma = 0
    peso = 2
    for d in reversed(numero):
        soma += int(d) * peso
        peso = 2 if peso == 9 else peso + 1
    return soma % 11


def modulo11_arrecadacao(numero: str) -> int:
    resto = _soma11(numero)
    return 0 if resto in (0, 1) else 11 - resto


def modulo11_boleto(numero: str) -> int:
    dv = 11 - _soma11(numero)
    return 1 if dv in (0, 10, 11) else dv


def _digitos(texto: str | None) -> str | None:
    if not texto or not _PERMITIDO.match(texto):
        return None
    return re.sub(r"\D", "", texto)


def _centavos(trecho: str) -> Decimal | None:
    valor = int(trecho)
    return (Decimal(valor) / 100).quantize(Decimal("0.01")) if valor > 0 else None


def _vencimento(fator: int, hoje: date) -> date | None:
    if fator < 1000:
        return None
    candidatos = [_BASE_ANTIGA + timedelta(days=fator), _BASE_NOVA + timedelta(days=fator - 1000)]
    return min(candidatos, key=lambda d: abs((d - hoje).days))


# ---------- arrecadação ----------

def _modulo_arrecadacao(codigo: str):
    return modulo10 if codigo[2] in "67" else modulo11_arrecadacao


def _arrecadacao(codigo: str, linha: str | None) -> CodigoLido:
    valido = codigo[2] in "6789"
    if valido:
        modulo = _modulo_arrecadacao(codigo)
        valido = int(codigo[3]) == modulo(codigo[:3] + codigo[4:])
        blocos = [codigo[i:i + 11] for i in range(0, 44, 11)]
        linha_calculada = "".join(b + str(modulo(b)) for b in blocos)
        if linha is not None:
            valido = valido and linha == linha_calculada
        linha = linha_calculada
    return CodigoLido(
        tipo="arrecadacao", codigo_barras=codigo, linha_digitavel=linha or "", valido=valido,
        valor=_centavos(codigo[4:15]) if valido and codigo[2] in "68" else None, vencimento=None,
    )


# ---------- boleto ----------

def _linha_do_boleto(codigo: str) -> str:
    c1 = codigo[0:4] + codigo[19:24]
    c2 = codigo[24:34]
    c3 = codigo[34:44]
    return (c1 + str(modulo10(c1)) + c2 + str(modulo10(c2)) + c3 + str(modulo10(c3))
            + codigo[4] + codigo[5:19])


def _codigo_do_boleto(linha: str) -> str:
    return linha[0:4] + linha[32] + linha[33:47] + linha[4:9] + linha[10:20] + linha[21:31]


def _boleto(codigo: str, linha: str | None, hoje: date) -> CodigoLido:
    valido = int(codigo[4]) == modulo11_boleto(codigo[:4] + codigo[5:])
    linha_calculada = _linha_do_boleto(codigo)
    if linha is not None:
        valido = valido and linha == linha_calculada
    return CodigoLido(
        tipo="boleto", codigo_barras=codigo, linha_digitavel=linha_calculada, valido=valido,
        valor=_centavos(codigo[9:19]) if valido else None,
        vencimento=_vencimento(int(codigo[5:9]), hoje) if valido else None,
    )


def analisar(texto: str | None, hoje: date) -> CodigoLido | None:
    """None = não parece código de barras nem linha digitável (tamanho ou caracteres errados)."""
    numeros = _digitos(texto)
    if numeros is None:
        return None
    if len(numeros) == 48 and numeros[0] == "8":
        codigo = "".join(numeros[i:i + 11] for i in range(0, 48, 12))
        return _arrecadacao(codigo, numeros)
    if len(numeros) == 47:
        return _boleto(_codigo_do_boleto(numeros), numeros, hoje)
    if len(numeros) == 44:
        return _arrecadacao(numeros, None) if numeros[0] == "8" else _boleto(numeros, None, hoje)
    return None
