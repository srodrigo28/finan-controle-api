import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modelos.base import ModeloBase, uuid_pk
from app.util import data_iso, iso, num, uid

TIPOS = ("despesa", "receita")
FORMAS_PAGAMENTO = ("dinheiro", "debito", "credito", "pix", "boleto", "outro")


class Lancamento(ModeloBase):
    __tablename__ = "lancamento"
    __table_args__ = (Index("ix_lancamento_usuario_data", "usuario_id", "data"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categoria.id", ondelete="SET NULL")
    )
    descricao: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    data: Mapped[date] = mapped_column(Date, nullable=False)
    forma_pagamento: Mapped[str | None] = mapped_column(String(12))
    sessao_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessao_compra.id", ondelete="SET NULL", use_alter=True, name="fk_lancamento_sessao_id")
    )
    conta_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conta_agendada.id", ondelete="SET NULL", use_alter=True, name="fk_lancamento_conta_id")
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    anexos: Mapped[list["Anexo"]] = relationship(
        back_populates="lancamento", cascade="all, delete-orphan", lazy="selectin"
    )

    def para_dict(self, itens: list | None = None) -> dict:
        d = {
            "id": str(self.id),
            "tipo": self.tipo,
            "valor": num(self.valor),
            "categoria_id": uid(self.categoria_id),
            "descricao": self.descricao,
            "data": data_iso(self.data),
            "forma_pagamento": self.forma_pagamento,
            "sessao_id": uid(self.sessao_id),
            "conta_id": uid(self.conta_id),
            "anexos": [a.para_dict() for a in self.anexos],
            "criado_em": iso(self.criado_em),
            "atualizado_em": iso(self.atualizado_em),
        }
        if itens is not None:
            d["itens"] = itens
        return d


class Anexo(ModeloBase):
    __tablename__ = "anexo"

    id: Mapped[uuid.UUID] = uuid_pk()
    lancamento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lancamento.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    caminho: Mapped[str] = mapped_column(String(300), nullable=False)
    tipo_mime: Mapped[str] = mapped_column(String(80), nullable=False)
    tamanho: Mapped[int] = mapped_column(Integer, nullable=False)

    lancamento: Mapped[Lancamento] = relationship(back_populates="anexos")

    def para_dict(self) -> dict:
        return {
            "id": str(self.id),
            "lancamento_id": str(self.lancamento_id),
            "nome": self.nome,
            "tipo_mime": self.tipo_mime,
            "tamanho": self.tamanho,
            "url": f"/api/v1/anexos/{self.id}/arquivo",
            "criado_em": iso(self.criado_em),
        }
