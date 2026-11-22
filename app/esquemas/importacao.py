import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import Field

from app.esquemas.comum import Esquema, ValorPositivo
from app.esquemas.lancamento import FormaPagamento, Tipo


class ContaNova(Esquema):
    nome: str = Field(min_length=1, max_length=120)
    dia_vencimento: int = Field(ge=1, le=31)


class ContaRascunho(Esquema):
    """Conta de consumo ou boleto (6c): para onde a linha vai e o que foi lido do documento."""

    conta_id: uuid.UUID | None = None
    casamento: Literal["chave_identificador", "chave", "identificador", "nome"] | None = None
    conta_nova: ContaNova | None = None
    vencimento: date | None = None
    pago: bool = False
    data_pagamento: date | None = None
    debito_automatico: bool = False
    referencia: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    consumo: Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=3)] | None = None
    unidade: Literal["kWh", "m3"] | None = None
    # O DV é conferido de novo no servidor ao confirmar; `codigo_valido` é só para a tela.
    linha_digitavel: str | None = Field(default=None, max_length=60)
    codigo_valido: bool = False
    emissor_nome: str | None = Field(default=None, max_length=120)
    emissor_chave: str | None = Field(default=None, max_length=40)
    identificador_cliente: str | None = Field(default=None, max_length=40)
    tipo_servico: Literal["agua", "luz", "gas", "internet", "telefone", "outro"] | None = None


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
    # Rascunho antigo (antes da 6c) não tem destino: vira lançamento, como sempre foi.
    destino: Literal["lancamento", "conta"] = "lancamento"
    conta: ContaRascunho | None = None


class AtualizarRascunho(Esquema):
    linhas: list[LinhaRascunho] = Field(max_length=500)
