import uuid
from decimal import Decimal

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.modelos.base import ModeloBase, uuid_pk
from app.util import iso, num

_hasher = PasswordHasher()


class Usuario(ModeloBase):
    __tablename__ = "usuario"

    id: Mapped[uuid.UUID] = uuid_pk()
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    moeda: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)
    orcamento_mensal: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    orcamento_diario: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    def definir_senha(self, senha: str) -> None:
        self.senha_hash = _hasher.hash(senha)

    def verificar_senha(self, senha: str) -> bool:
        try:
            return _hasher.verify(self.senha_hash, senha)
        except VerifyMismatchError:
            return False

    def para_dict(self) -> dict:
        return {
            "id": str(self.id),
            "nome": self.nome,
            "email": self.email,
            "moeda": self.moeda,
            "orcamento_mensal": num(self.orcamento_mensal),
            "orcamento_diario": num(self.orcamento_diario),
            "criado_em": iso(self.criado_em),
        }
