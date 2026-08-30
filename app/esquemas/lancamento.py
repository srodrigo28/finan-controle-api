import uuid
from datetime import date
from typing import Literal

from pydantic import Field

from app.esquemas.comum import Esquema, ValorPositivo

Tipo = Literal["despesa", "receita"]
FormaPagamento = Literal["dinheiro", "debito", "credito", "pix", "boleto", "outro"]


class CriarLancamento(Esquema):
    id: uuid.UUID | None = None
    tipo: Tipo
    valor: ValorPositivo
    categoria_id: uuid.UUID | None = None
    descricao: str = Field(default="", max_length=200)
    data: date
    forma_pagamento: FormaPagamento | None = None


class AtualizarLancamento(Esquema):
    tipo: Tipo | None = None
    valor: ValorPositivo | None = None
    categoria_id: uuid.UUID | None = None
    descricao: str | None = Field(default=None, max_length=200)
    data: date | None = None
    forma_pagamento: FormaPagamento | None = None
