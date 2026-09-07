import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import Boolean, DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.modelos.base import ModeloBase, uuid_pk
from app.util import iso, num

_hasher = PasswordHasher()
DIAS_TESTE = 30


def _fim_do_teste() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=DIAS_TESTE)


class Usuario(ModeloBase):
    __tablename__ = "usuario"

    id: Mapped[uuid.UUID] = uuid_pk()
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    moeda: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)
    orcamento_mensal: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    orcamento_diario: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # Plano: "teste" (30 dias gratis, sem cartao) ou "completo". Cobranca ainda nao implementada.
    plano: Mapped[str] = mapped_column(String(20), default="teste", server_default="teste", nullable=False)
    teste_expira_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=_fim_do_teste)
    # Sem e-mail confirmado a conta existe mas não usa o app: o `before_request`
    # da fábrica barra tudo fora de `/auth/*` com 403 EMAIL_NAO_VERIFICADO.
    email_verificado: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    email_verificado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def dias_restantes_teste(self) -> int | None:
        if self.plano != "teste" or self.teste_expira_em is None:
            return None
        restante = self.teste_expira_em - datetime.now(timezone.utc)
        return max(0, (restante.days + (1 if restante.seconds > 0 else 0)))

    @property
    def teste_ativo(self) -> bool:
        return self.plano == "completo" or (self.dias_restantes_teste or 0) > 0

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
            "plano": self.plano,
            "teste_expira_em": iso(self.teste_expira_em) if self.teste_expira_em else None,
            "dias_restantes_teste": self.dias_restantes_teste,
            "teste_ativo": self.teste_ativo,
            "email_verificado": self.email_verificado,
            "email_verificado_em": iso(self.email_verificado_em) if self.email_verificado_em else None,
            "criado_em": iso(self.criado_em),
        }
