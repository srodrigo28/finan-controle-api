import uuid

from pydantic import Field

from app.esquemas.comum import Cor, Esquema, Valor


class CriarCategoria(Esquema):
    id: uuid.UUID | None = None
    nome: str = Field(min_length=1, max_length=80)
    cor: Cor = "#6366F1"
    icone: str = Field(default="tag", max_length=60)
    pai_id: uuid.UUID | None = None
    orcamento_mensal: Valor | None = None


class AtualizarCategoria(Esquema):
    nome: str | None = Field(default=None, min_length=1, max_length=80)
    cor: Cor | None = None
    icone: str | None = Field(default=None, max_length=60)
    pai_id: uuid.UUID | None = None
    orcamento_mensal: Valor | None = None
    arquivada: bool | None = None
    ordem: int | None = Field(default=None, ge=0)


class Reordenar(Esquema):
    ids: list[uuid.UUID] = Field(min_length=1)
