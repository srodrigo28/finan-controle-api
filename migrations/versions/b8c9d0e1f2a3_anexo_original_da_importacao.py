"""anexo aponta para o original da importação (anexo.importacao_id) + anexa os já importados

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-22

O lançamento confirmado de uma importação ganha o original como anexo, sem copiar o arquivo
(armazenamento = "importacao"). Os lançamentos importados antes disto recebem o anexo aqui.
Prompt: docs/prompts/2026-11/21-novembro-importar-imagem-pdf-com-ia.md (F6)
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "anexo",
        sa.Column("importacao_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("importacao.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_anexo_importacao_id", "anexo", ["importacao_id"])

    conexao = op.get_bind()
    pendentes = conexao.execute(sa.text(
        """
        SELECT l.id AS lancamento_id, i.id AS importacao_id, i.nome, i.tipo_mime, i.tamanho
        FROM lancamento l JOIN importacao i ON i.id = l.importacao_id
        WHERE NOT EXISTS (SELECT 1 FROM anexo a WHERE a.lancamento_id = l.id AND a.importacao_id = i.id)
        """
    )).mappings().all()
    for p in pendentes:
        conexao.execute(
            sa.text(
                "INSERT INTO anexo (id, lancamento_id, nome, tipo_mime, tamanho, armazenamento, importacao_id) "
                "VALUES (:id, :lid, :nome, :mime, :tam, 'importacao', :iid)"
            ),
            {"id": uuid.uuid4(), "lid": p["lancamento_id"], "nome": p["nome"], "mime": p["tipo_mime"],
             "tam": p["tamanho"], "iid": p["importacao_id"]},
        )


def downgrade():
    op.execute("DELETE FROM anexo WHERE armazenamento = 'importacao'")
    op.drop_index("ix_anexo_importacao_id", table_name="anexo")
    op.drop_column("anexo", "importacao_id")
