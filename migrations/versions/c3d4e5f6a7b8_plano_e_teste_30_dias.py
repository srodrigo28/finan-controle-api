"""plano e teste de 30 dias no usuario

Revision ID: c3d4e5f6a7b8
Revises: bc8b90ab66dd
Create Date: 2026-08-30
"""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "bc8b90ab66dd"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("usuario", sa.Column("plano", sa.String(length=20), server_default="teste", nullable=False))
    op.add_column("usuario", sa.Column("teste_expira_em", sa.DateTime(timezone=True), nullable=True))
    # quem ja existe ganha os 30 dias contados do cadastro
    op.execute("UPDATE usuario SET teste_expira_em = criado_em + INTERVAL '30 days' WHERE teste_expira_em IS NULL")


def downgrade():
    op.drop_column("usuario", "teste_expira_em")
    op.drop_column("usuario", "plano")
