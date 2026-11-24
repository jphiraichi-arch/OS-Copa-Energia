"""alertas de erro grave: contadores e o tipo 'alerta_erro' na fila de e-mails

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-24

Upgrade:
- alertas_erro (impressão digital, último alerta, última ocorrência, ocorrências
  pendentes) e alertas_dia (dia, e-mails enviados): contadores dos limites de alerta,
  no banco para valerem entre processos. Sem mensagem de erro nem dado de usuário.
- email_fila.tipo passa a aceitar 'alerta_erro' (o CHECK é recriado).
Downgrade: apaga da fila as mensagens 'alerta_erro' (são só avisos técnicos), volta o
CHECK anterior e apaga as duas tabelas.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from osapp.models.tipos import DataHoraUTC

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIPOS_ANTES = "tipo IN ('nova_solicitacao', 'codigo_confirmacao')"
TIPOS_DEPOIS = "tipo IN ('nova_solicitacao', 'codigo_confirmacao', 'alerta_erro')"


def upgrade() -> None:
    op.create_table(
        "alertas_erro",
        sa.Column("impressao", sa.String(length=200), nullable=False),
        sa.Column("ultimo_alerta_em", DataHoraUTC(), nullable=True),
        sa.Column("ultima_ocorrencia_em", DataHoraUTC(), nullable=False),
        sa.Column("ocorrencias_pendentes", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("impressao", name=op.f("pk_alertas_erro")),
    )
    op.create_table(
        "alertas_dia",
        sa.Column("dia", sa.Date(), nullable=False),
        sa.Column("emails", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("dia", name=op.f("pk_alertas_dia")),
    )
    with op.batch_alter_table("email_fila", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_email_fila_tipo_valido"), type_="check")
        batch_op.create_check_constraint(op.f("ck_email_fila_tipo_valido"), TIPOS_DEPOIS)


def downgrade() -> None:
    fila = sa.table("email_fila", sa.column("tipo", sa.String()))
    op.execute(fila.delete().where(fila.c.tipo == "alerta_erro"))
    with op.batch_alter_table("email_fila", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_email_fila_tipo_valido"), type_="check")
        batch_op.create_check_constraint(op.f("ck_email_fila_tipo_valido"), TIPOS_ANTES)
    op.drop_table("alertas_dia")
    op.drop_table("alertas_erro")
