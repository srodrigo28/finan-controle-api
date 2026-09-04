import uuid
from datetime import date
from typing import Literal

from pydantic import Field

from app.esquemas.comum import Esquema, Valor
from app.esquemas.lancamento import FormaPagamento

Recorrencia = Literal["mensal", "semanal", "anual", "unica"]


class CriarConta(Esquema):
    id: uuid.UUID | None = None
    nome: str = Field(min_length=1, max_length=120)
    valor_estimado: Valor | None = None
    dia_vencimento: int = Field(ge=1, le=31)
    recorrencia: Recorrencia = "mensal"
    categoria_id: uuid.UUID | None = None
    lembrete_dias: int = Field(default=3, ge=0, le=60)
    mes_referencia: int | None = Field(default=None, ge=1, le=12)
    ano_referencia: int | None = Field(default=None, ge=2000, le=2100)


class AtualizarConta(Esquema):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    valor_estimado: Valor | None = None
    dia_vencimento: int | None = Field(default=None, ge=1, le=31)
    recorrencia: Recorrencia | None = None
    categoria_id: uuid.UUID | None = None
    ativa: bool | None = None
    lembrete_dias: int | None = Field(default=None, ge=0, le=60)
    mes_referencia: int | None = Field(default=None, ge=1, le=12)
    ano_referencia: int | None = Field(default=None, ge=2000, le=2100)


class AtualizarOcorrencia(Esquema):
    """Ajuste pontual de um mês: valor diferente, vencimento adiado ou "esse mês não tem"."""

    valor_real: Valor | None = None
    vencimento: date | None = None
    status: Literal["pendente", "pulada"] | None = None


class PagarOcorrencia(Esquema):
    valor_real: Valor
    data: date | None = None
    forma_pagamento: FormaPagamento | None = None
