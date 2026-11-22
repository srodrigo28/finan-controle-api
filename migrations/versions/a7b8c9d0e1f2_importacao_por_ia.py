"""importacao por IA: tabela importacao + lancamento.importacao_id

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-21

O documento original (foto/PDF) fica em disco e a linha guarda o rascunho lido pelo Claude.
Prompt: docs/prompts/2026-11/21-novembro-importar-imagem-pdf-com-ia.md
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "importacao",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False),
        sa.Column("tipo_documento", sa.String(20)),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("tipo_mime", sa.String(80), nullable=False),
        sa.Column("tamanho", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("caminho", sa.String(300), nullable=False),
        sa.Column("modelo_ia", sa.String(60)),
        sa.Column("tokens_entrada", sa.Integer()),
        sa.Column("tokens_saida", sa.Integer()),
        sa.Column("tentativas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("resultado", postgresql.JSONB()),
        sa.Column("erro", sa.String(300)),
        sa.Column("concluida_em", sa.DateTime(timezone=True)),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_importacao_usuario_criado", "importacao", ["usuario_id", "criado_em"])
    op.create_index("ix_importacao_usuario_sha256", "importacao", ["usuario_id", "sha256"])
    op.add_column("lancamento", sa.Column("importacao_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_lancamento_importacao_id", "lancamento", "importacao", ["importacao_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_lancamento_importacao_id", "lancamento", ["importacao_id"])


def downgrade():
    op.drop_index("ix_lancamento_importacao_id", table_name="lancamento")
    op.drop_constraint("fk_lancamento_importacao_id", "lancamento", type_="foreignkey")
    op.drop_column("lancamento", "importacao_id")
    op.drop_index("ix_importacao_usuario_sha256", table_name="importacao")
    op.drop_index("ix_importacao_usuario_criado", table_name="importacao")
    op.drop_table("importacao")
