"""motivos de cancelamento (prompt 41)

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-25

Upgrade: motivos_cancelamento (codigo único, nome, ordem, ativo) com 'Fora do escopo (TI)',
'Duplicada', 'Aberta por engano' e 'Outro'; ordens_servico.motivo_cancelamento_id (FK) e
motivo_cancelamento_texto (até 300), vazios nas ordens canceladas antes.
Downgrade: apaga as duas colunas e a tabela. Os motivos gravados se perdem; os eventos
STATUS do cancelamento continuam com a observação (motivo em texto) no histórico.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INICIAIS = (
    ("FORA_ESCOPO_TI", "Fora do escopo (TI)", 1),
    ("DUPLICADA", "Duplicada", 2),
    ("ENGANO", "Aberta por engano", 3),
    ("OUTRO", "Outro", 4),
)


def upgrade() -> None:
    tabela = op.create_table(
        "motivos_cancelamento",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=30), nullable=False),
        sa.Column("nome", sa.String(length=60), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_motivos_cancelamento")),
        sa.UniqueConstraint("codigo", name=op.f("uq_motivos_cancelamento_codigo")),
    )
    op.bulk_insert(tabela, [{"codigo": c, "nome": n, "ordem": o} for c, n, o in INICIAIS])
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.add_column(sa.Column("motivo_cancelamento_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("motivo_cancelamento_texto", sa.String(length=300), nullable=True)
        )
        batch_op.create_foreign_key(
            op.f("fk_ordens_servico_motivo_cancelamento_id_motivos_cancelamento"),
            "motivos_cancelamento",
            ["motivo_cancelamento_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f("fk_ordens_servico_motivo_cancelamento_id_motivos_cancelamento"),
            type_="foreignkey",
        )
        batch_op.drop_column("motivo_cancelamento_texto")
        batch_op.drop_column("motivo_cancelamento_id")
    op.drop_table("motivos_cancelamento")
