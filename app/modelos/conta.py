import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.modelos.base import ModeloBase, uuid_pk
from app.util import data_iso, iso, num, uid

RECORRENCIAS = ("mensal", "semanal", "anual", "unica")
STATUS_OCORRENCIA = ("pendente", "paga", "atrasada")


class ContaAgendada(ModeloBase):
    __tablename__ = "conta_agendada"

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    valor_estimado: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    dia_vencimento: Mapped[int] = mapped_column(Integer, nullable=False)
    recorrencia: Mapped[str] = mapped_column(String(10), default="mensal", nullable=False)
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categoria.id", ondelete="SET NULL")
    )
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    lembrete_dias: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Para recorrência anual/unica: mês (1-12) e ano de referência do vencimento.
    mes_referencia: Mapped[int | None] = mapped_column(Integer)
    ano_referencia: Mapped[int | None] = mapped_column(Integer)

    ocorrencias: Mapped[list["OcorrenciaConta"]] = relationship(
        back_populates="conta", cascade="all, delete-orphan"
    )

    def para_dict(self) -> dict:
        return {
            "id": str(self.id),
            "nome": self.nome,
            "valor_estimado": num(self.valor_estimado),
            "dia_vencimento": self.dia_vencimento,
            "recorrencia": self.recorrencia,
            "categoria_id": uid(self.categoria_id),
            "ativa": self.ativa,
            "lembrete_dias": self.lembrete_dias,
            "mes_referencia": self.mes_referencia,
            "ano_referencia": self.ano_referencia,
            "criado_em": iso(self.criado_em),
        }


class OcorrenciaConta(ModeloBase):
    __tablename__ = "ocorrencia_conta"
    __table_args__ = (
        UniqueConstraint("conta_id", "competencia", "vencimento", name="uq_ocorrencia_conta_competencia"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    conta_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conta_agendada.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competencia: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    vencimento: Mapped[date] = mapped_column(Date, nullable=False)
    valor_real: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(10), default="pendente", nullable=False)
    lancamento_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lancamento.id", ondelete="SET NULL")
    )

    conta: Mapped[ContaAgendada] = relationship(back_populates="ocorrencias", lazy="joined")

    def status_efetivo(self, hoje: date) -> str:
        if self.status == "paga":
            return "paga"
        return "atrasada" if self.vencimento < hoje else "pendente"

    def para_dict(self, hoje: date | None = None) -> dict:
        hoje = hoje or date.today()
        return {
            "id": str(self.id),
            "conta_id": str(self.conta_id),
            "competencia": self.competencia,
            "vencimento": data_iso(self.vencimento),
            "valor_real": num(self.valor_real),
            "status": self.status_efetivo(hoje),
            "lancamento_id": uid(self.lancamento_id),
            "conta": {
                "nome": self.conta.nome,
                "categoria_id": uid(self.conta.categoria_id),
                "valor_estimado": num(self.conta.valor_estimado),
            },
        }
