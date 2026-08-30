import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.modelos.base import ModeloBase, uuid_pk
from app.util import iso


class InscricaoPush(ModeloBase):
    """Assinatura Web Push de um aparelho (PWA instalado). Um usuário pode ter várias."""

    __tablename__ = "inscricao_push"

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False, index=True
    )
    endpoint: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    aparelho: Mapped[str | None] = mapped_column(String(200))
    ultimo_envio_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_erro: Mapped[str | None] = mapped_column(String(200))

    def para_dict(self) -> dict:
        return {
            "id": str(self.id),
            "aparelho": self.aparelho,
            "criado_em": iso(self.criado_em),
            "ultimo_envio_em": iso(self.ultimo_envio_em) if self.ultimo_envio_em else None,
        }

    def como_assinatura(self) -> dict:
        return {"endpoint": self.endpoint, "keys": {"p256dh": self.p256dh, "auth": self.auth}}
