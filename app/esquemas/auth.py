from pydantic import EmailStr, Field

from app.esquemas.comum import Esquema, Valor


SENHA_MINIMA = 8


class Registrar(Esquema):
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr
    # 8 é o mínimo que o formulário do front já pedia; o back exigia 6 e deixava
    # passar senha que a própria tela recusava.
    senha: str = Field(min_length=SENHA_MINIMA, max_length=128)


class Login(Esquema):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=128)


class ConfirmarCodigo(Esquema):
    codigo: str = Field(pattern=r"^\d{4}$")


class ConfirmarToken(Esquema):
    token: str = Field(min_length=10, max_length=200)


class EsqueciSenha(Esquema):
    email: EmailStr


class RedefinirSenha(Esquema):
    token: str = Field(min_length=10, max_length=200)
    senha: str = Field(min_length=SENHA_MINIMA, max_length=128)


class AtualizarEu(Esquema):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    orcamento_mensal: Valor | None = None
    orcamento_diario: Valor | None = None
