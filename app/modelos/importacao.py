"""Importação por IA: o documento original (foto ou PDF) e o rascunho de lançamentos lido dele."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.modelos.base import ModeloBase, uuid_pk
from app.util import iso

# recebida → [senha →] lendo → revisar → concluida | erro (dá para reler) | descartada (o original fica guardado)
# `senha`: PDF protegido esperando a senha do usuário (POST /importacoes/<id>/senha); nada foi cobrado.
ESTADOS = ("recebida", "senha", "lendo", "revisar", "concluida", "erro", "descartada")


class Importacao(ModeloBase):
    __tablename__ = "importacao"
    __table_args__ = (
        Index("ix_importacao_usuario_criado", "usuario_id", "criado_em"),
        Index("ix_importacao_usuario_sha256", "usuario_id", "sha256"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False
    )
    estado: Mapped[str] = mapped_column(String(12), nullable=False, default="recebida")
    tipo_documento: Mapped[str | None] = mapped_column(String(20))
    # Original: sempre em disco (UPLOAD_DIR/importacoes/<usuario>/), servido só pela API com JWT.
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo_mime: Mapped[str] = mapped_column(String(80), nullable=False)
    tamanho: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    caminho: Mapped[str] = mapped_column(String(300), nullable=False)
    modelo_ia: Mapped[str | None] = mapped_column(String(60))
    tokens_entrada: Mapped[int | None] = mapped_column(Integer)
    tokens_saida: Mapped[int | None] = mapped_column(Integer)
    # Leituras pagas deste documento (a 1ª + cada "ler de novo"); teto em servicos/importacoes.py.
    tentativas: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    # {"estabelecimento", "observacao", "linhas": [{"data", "valor", "tipo", "descricao", "categoria_id",
    #   "forma_pagamento", "confianca", "incluir"}]} — o rascunho que o usuário edita antes de confirmar.
    resultado: Mapped[dict | None] = mapped_column(JSONB)
    erro: Mapped[str | None] = mapped_column(String(300))
    concluida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Muda a cada troca de estado: leitura presa em `lendo` (worker reiniciou) é detectada por ele.
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def para_dict(self) -> dict:
        r = self.resultado or {}
        return {
            "id": str(self.id),
            "estado": self.estado,
            "tipo_documento": self.tipo_documento,
            "nome": self.nome,
            "tipo_mime": self.tipo_mime,
            "tamanho": self.tamanho,
            "url": f"/api/v1/importacoes/{self.id}/arquivo",
            "estabelecimento": r.get("estabelecimento"),
            "observacao": r.get("observacao"),
            "linhas": r.get("linhas", []),
            "lancamentos_criados": r.get("lancamentos_criados", []),
            "ocorrencias_afetadas": r.get("ocorrencias_afetadas", []),
            "erro": self.erro,
            "modelo_ia": self.modelo_ia,
            "tentativas": self.tentativas,
            "criado_em": iso(self.criado_em),
            "concluida_em": iso(self.concluida_em),
        }
