import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.modelos.base import ModeloBase, uuid_pk
from app.util import iso, num, uid


class Categoria(ModeloBase):
    __tablename__ = "categoria"

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(String(80), nullable=False)
    cor: Mapped[str] = mapped_column(String(9), default="#6366F1", nullable=False)
    icone: Mapped[str] = mapped_column(String(60), default="tag", nullable=False)
    pai_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categoria.id", ondelete="SET NULL"))
    orcamento_mensal: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    arquivada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    def para_dict(self) -> dict:
        return {
            "id": str(self.id),
            "nome": self.nome,
            "cor": self.cor,
            "icone": self.icone,
            "pai_id": uid(self.pai_id),
            "orcamento_mensal": num(self.orcamento_mensal),
            "arquivada": self.arquivada,
            "ordem": self.ordem,
            "criado_em": iso(self.criado_em),
        }
