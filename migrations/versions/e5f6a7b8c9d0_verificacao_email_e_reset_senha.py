"""verificacao de email (codigo de 4 digitos) e reset de senha

Revision ID: e5f6a7b8c9d0
Revises: 74b0d8176769
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e5f6a7b8c9d0"
down_revision = "74b0d8176769"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("usuario", sa.Column("email_verificado", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("usuario", sa.Column("email_verificado_em", sa.DateTime(timezone=True), nullable=True))
    # Quem JA usava o sistema entra como verificado. Sem isto, a trava do
    # `before_request` prenderia todas as contas existentes na tela do codigo,
    # sem nunca terem recebido um e-mail.
    op.execute("UPDATE usuario SET email_verificado = true, email_verificado_em = criado_em")

    op.create_table(
        "codigo_verificacao",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuario.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("finalidade", sa.String(length=20), nullable=False),
        sa.Column("codigo_hash", sa.String(length=64), nullable=True),
        # unicidade pelo INDICE (e nao por constraint separada): e assim que o
        # modelo declara (`unique=True, index=True`), e `flask db check` acusa a
        # diferenca se as duas formas divergirem.
        sa.Column("token_hash", sa.String(length=64), nullable=True),
        sa.Column("tentativas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_codigo_verificacao_usuario_id", "codigo_verificacao", ["usuario_id"])
    op.create_index("ix_codigo_verificacao_finalidade", "codigo_verificacao", ["finalidade"])
    op.create_index("ix_codigo_verificacao_token_hash", "codigo_verificacao", ["token_hash"], unique=True)


def downgrade():
    op.drop_table("codigo_verificacao")
    op.drop_column("usuario", "email_verificado_em")
    op.drop_column("usuario", "email_verificado")
