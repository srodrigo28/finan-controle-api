import uuid
from datetime import date
from typing import Literal

from pydantic import Field

from app.esquemas.comum import Esquema, ValorPositivo
from app.esquemas.lancamento import FormaPagamento, Tipo


class LinhaRascunho(Esquema):
    """Uma linha do rascunho como o usuário deixou na revisão."""

    data: date | None = None
    valor: ValorPositivo | None = None
    tipo: Tipo = "despesa"
    descricao: str = Field(default="", max_length=200)
    categoria_id: uuid.UUID | None = None
    forma_pagamento: FormaPagamento | None = None
    confianca: Literal["alta", "media", "baixa"] = "media"
    incluir: bool = True


class AtualizarRascunho(Esquema):
    linhas: list[LinhaRascunho] = Field(max_length=500)
