"""conta de consumo importada: chave da companhia na conta e o que foi lido na ocorrência do mês

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-11-22

Conta de água, luz, gás ou boleto lido pela IA preenche a ocorrência do mês (valor, vencimento, código para
copiar, consumo) e guarda de qual importação veio. A conta ganha a chave da companhia e o nº da instalação,
para o mês seguinte casar sozinho. Tudo nulo: nada muda para as contas que já existem.
Prompt: docs/prompts/2026-11/21-novembro-importar-imagem-pdf-com-ia.md (F6c)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("conta_agendada", sa.Column("emissor_chave", sa.String(40)))
    op.add_column("conta_agendada", sa.Column("identificador_cliente", sa.String(40)))
    op.add_column("conta_agendada", sa.Column("tipo_servico", sa.String(10)))
    op.create_index("ix_conta_agendada_usuario_emissor", "conta_agendada", ["usuario_id", "emissor_chave"])

    op.add_column(
        "ocorrencia_conta",
        sa.Column("importacao_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("importacao.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_ocorrencia_conta_importacao_id", "ocorrencia_conta", ["importacao_id"])
    op.add_column("ocorrencia_conta", sa.Column("linha_digitavel", sa.String(48)))
    op.add_column("ocorrencia_conta", sa.Column("consumo", sa.Numeric(10, 3)))
    op.add_column("ocorrencia_conta", sa.Column("unidade_consumo", sa.String(5)))
    op.add_column("ocorrencia_conta", sa.Column("referencia", sa.String(7)))


def downgrade():
    op.drop_column("ocorrencia_conta", "referencia")
    op.drop_column("ocorrencia_conta", "unidade_consumo")
    op.drop_column("ocorrencia_conta", "consumo")
    op.drop_column("ocorrencia_conta", "linha_digitavel")
    op.drop_index("ix_ocorrencia_conta_importacao_id", table_name="ocorrencia_conta")
    op.drop_column("ocorrencia_conta", "importacao_id")
    op.drop_index("ix_conta_agendada_usuario_emissor", table_name="conta_agendada")
    op.drop_column("conta_agendada", "tipo_servico")
    op.drop_column("conta_agendada", "identificador_cliente")
    op.drop_column("conta_agendada", "emissor_chave")
