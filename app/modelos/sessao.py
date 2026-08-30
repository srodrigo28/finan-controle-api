import uuid
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modelos.base import ModeloBase, uuid_pk
from app.util import data_iso, iso, num, uid

STATUS_SESSAO = ("aberta", "fechada", "abandonada")


class SessaoCompra(ModeloBase):
    __tablename__ = "sessao_compra"

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False, index=True
    )
    local: Mapped[str | None] = mapped_column(String(120))
    orcamento: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(12), default="aberta", nullable=False)
    aberta_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fechada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_carrinho: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    total_pago: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    motivo_divergencia: Mapped[str | None] = mapped_column(String(200))
    lancamento_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lancamento.id", ondelete="SET NULL", use_alter=True, name="fk_sessao_compra_lancamento_id")
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    itens: Mapped[list["ItemCompra"]] = relationship(
        back_populates="sessao", cascade="all, delete-orphan", lazy="selectin", order_by="ItemCompra.criado_em"
    )

    def calcular_total(self) -> Decimal:
        return sum((i.subtotal for i in self.itens if not i.removido), Decimal("0.00"))

    def para_dict(self, com_itens: bool = True) -> dict:
        total = self.total_carrinho if self.status != "aberta" and self.total_carrinho is not None else self.calcular_total()
        d = {
            "id": str(self.id),
            "local": self.local,
            "orcamento": num(self.orcamento),
            "status": self.status,
            "aberta_em": iso(self.aberta_em),
            "fechada_em": iso(self.fechada_em),
            "total_carrinho": num(total),
            "total_pago": num(self.total_pago),
            "motivo_divergencia": self.motivo_divergencia,
            "lancamento_id": uid(self.lancamento_id),
            "atualizado_em": iso(self.atualizado_em),
        }
        if com_itens:
            d["itens"] = [i.para_dict() for i in self.itens]
        return d


class ItemCompra(ModeloBase):
    __tablename__ = "item_compra"

    id: Mapped[uuid.UUID] = uuid_pk()
    sessao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessao_compra.id", ondelete="CASCADE"), nullable=False, index=True
    )
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categoria.id", ondelete="SET NULL")
    )
    valor_unitario: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False, default=Decimal("1"))
    removido: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    sessao: Mapped[SessaoCompra] = relationship(back_populates="itens")

    @property
    def subtotal(self) -> Decimal:
        # Arredondamento comercial (meio para cima), como no caixa do mercado.
        return (self.valor_unitario * self.quantidade).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def para_dict(self) -> dict:
        return {
            "id": str(self.id),
            "sessao_id": str(self.sessao_id),
            "descricao": self.descricao,
            "categoria_id": uid(self.categoria_id),
            "valor_unitario": num(self.valor_unitario),
            "quantidade": num(self.quantidade),
            "subtotal": num(self.subtotal),
            "removido": self.removido,
            "criado_em": iso(self.criado_em),
            "atualizado_em": iso(self.atualizado_em),
        }


class PrecoHistorico(ModeloBase):
    __tablename__ = "preco_historico"
    __table_args__ = (Index("ix_preco_usuario_descricao", "usuario_id", "descricao_normalizada"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False
    )
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao_normalizada: Mapped[str] = mapped_column(String(200), nullable=False)
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categoria.id", ondelete="SET NULL")
    )
    valor_unitario: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    sessao_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessao_compra.id", ondelete="CASCADE")
    )

    def para_dict(self) -> dict:
        return {
            "descricao": self.descricao,
            "descricao_normalizada": self.descricao_normalizada,
            "categoria_id": uid(self.categoria_id),
            "valor_unitario": num(self.valor_unitario),
            "data": data_iso(self.data),
            "sessao_id": uid(self.sessao_id),
        }
