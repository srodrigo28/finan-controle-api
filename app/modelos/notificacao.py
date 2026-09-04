import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
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


class Notificacao(ModeloBase):
    """Fila da central de notificações do app (o sino).

    A `chave` é o que dá identidade a um aviso: o motor de insights recalcula tudo a cada sincronização,
    e sem ela o mesmo aviso viraria linha nova toda vez. Com ela, sincronizar é um upsert — cria o que
    é novo, atualiza o texto do que mudou e fecha (`resolvida_em`) o que deixou de aparecer.
    A linha **nunca** é apagada: o histórico fica.
    """

    __tablename__ = "notificacao"
    __table_args__ = (UniqueConstraint("usuario_id", "chave", name="uq_notificacao_usuario_chave"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chave: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo: Mapped[str] = mapped_column(String(40), nullable=False)
    nivel: Mapped[str] = mapped_column(String(10), default="info", nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    corpo: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(200))
    lida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolvida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def para_dict(self) -> dict:
        return {
            "id": str(self.id),
            "chave": self.chave,
            "tipo": self.tipo,
            "nivel": self.nivel,
            "titulo": self.titulo,
            "corpo": self.corpo,
            "link": self.link,
            "lida": self.lida_em is not None,
            "resolvida": self.resolvida_em is not None,
            "criado_em": iso(self.criado_em),
        }
