"""anexos no bucket e inscricoes de push

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("anexo", sa.Column("armazenamento", sa.String(length=10), server_default="disco", nullable=False))
    op.add_column("anexo", sa.Column("bucket_file_id", sa.Integer(), nullable=True))
    op.add_column("anexo", sa.Column("url_publica", sa.String(length=500), nullable=True))
    op.alter_column("anexo", "caminho", existing_type=sa.String(length=300), nullable=True)

    op.create_table(
        "inscricao_push",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(length=255), nullable=False),
        sa.Column("auth", sa.String(length=255), nullable=False),
        sa.Column("aparelho", sa.String(length=200), nullable=True),
        sa.Column("ultimo_envio_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultimo_erro", sa.String(length=200), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint"),
    )
    op.create_index("ix_inscricao_push_usuario_id", "inscricao_push", ["usuario_id"])


def downgrade():
    op.drop_index("ix_inscricao_push_usuario_id", table_name="inscricao_push")
    op.drop_table("inscricao_push")
    op.alter_column("anexo", "caminho", existing_type=sa.String(length=300), nullable=False)
    op.drop_column("anexo", "url_publica")
    op.drop_column("anexo", "bucket_file_id")
    op.drop_column("anexo", "armazenamento")
