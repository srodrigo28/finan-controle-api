import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.esquemas.comum import Esquema, Quantidade, Valor
from app.esquemas.lancamento import FormaPagamento


class CriarSessao(Esquema):
    id: uuid.UUID | None = None
    local: str | None = Field(default=None, max_length=120)
    orcamento: Valor | None = None


class AtualizarSessao(Esquema):
    local: str | None = Field(default=None, max_length=120)
    orcamento: Valor | None = None


class CriarItem(Esquema):
    id: uuid.UUID | None = None
    descricao: str = Field(min_length=1, max_length=200)
    categoria_id: uuid.UUID | None = None
    valor_unitario: Valor
    quantidade: Quantidade = Decimal("1")


class AtualizarItem(Esquema):
    descricao: str | None = Field(default=None, min_length=1, max_length=200)
    categoria_id: uuid.UUID | None = None
    valor_unitario: Valor | None = None
    quantidade: Quantidade | None = None
    removido: bool | None = None


class FecharSessao(Esquema):
    total_pago: Valor
    motivo_divergencia: str | None = Field(default=None, max_length=200)
    categoria_id: uuid.UUID | None = None
    forma_pagamento: FormaPagamento | None = None


class ItemSincronizacao(Esquema):
    id: uuid.UUID
    descricao: str = Field(min_length=1, max_length=200)
    categoria_id: uuid.UUID | None = None
    valor_unitario: Valor
    quantidade: Quantidade
    removido: bool = False
    criado_em: datetime | None = None
    atualizado_em: datetime | None = None


class SessaoSincronizacao(Esquema):
    id: uuid.UUID
    local: str | None = Field(default=None, max_length=120)
    orcamento: Valor | None = None
    status: Literal["aberta", "fechada", "abandonada"] = "aberta"
    aberta_em: datetime | None = None
    fechada_em: datetime | None = None
    total_pago: Valor | None = None
    motivo_divergencia: str | None = Field(default=None, max_length=200)
    categoria_id: uuid.UUID | None = None
    forma_pagamento: FormaPagamento | None = None
    atualizado_em: datetime | None = None
    itens: list[ItemSincronizacao] = Field(default_factory=list)


class Sincronizar(Esquema):
    sessoes: list[SessaoSincronizacao] = Field(min_length=1)
