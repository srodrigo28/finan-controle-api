from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Valor = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
ValorPositivo = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Quantidade = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=3)]
Cor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]


class Esquema(BaseModel):
    """Base: ignora chaves desconhecidas, remove espaços de strings."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    def campos_enviados(self) -> dict:
        """Somente os campos presentes no JSON (para PATCH)."""
        return self.model_dump(exclude_unset=True)
