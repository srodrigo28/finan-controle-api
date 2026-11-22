"""auth_version no usuario (redefinir a senha revoga access/refresh antigos)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-21

A coluna nasceu em 09/09 DENTRO da e5f6a7b8c9d0, que ja estava aplicada em producao desde 07/09 — o
deploy nao a criaria e o model consultaria uma coluna inexistente. Migration publicada nao se edita;
ver docs/spec/ERROS.md (E001) e a skill `migration`.
"""
from alembic import op
import sqlalchemy as sa

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("usuario", sa.Column("auth_version", sa.Integer(), server_default="0", nullable=False))


def downgrade():
    op.drop_column("usuario", "auth_version")
