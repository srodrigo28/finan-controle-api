from pydantic import EmailStr, Field

from app.esquemas.comum import Esquema, Valor


class Registrar(Esquema):
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr
    senha: str = Field(min_length=6, max_length=128)


class Login(Esquema):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=128)


class AtualizarEu(Esquema):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    orcamento_mensal: Valor | None = None
    orcamento_diario: Valor | None = None
