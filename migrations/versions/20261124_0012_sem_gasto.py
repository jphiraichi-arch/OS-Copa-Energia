"""fase sem gasto (prompt 31)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-24

Upgrade: ordens_servico.sem_gasto_previsto e sem_gasto_realizado (booleanos, não nulos,
padrão falso). Nenhuma ordem existente é alterada: as que já estão em execução ou
concluídas sem itens numa fase aparecem em `python -m osapp.cli listar-sem-itens` e são
corrigidas, depois de revisadas, com `marcar-sem-gasto NUMERO previsto|realizado`.
Downgrade: remove as duas colunas (as marcas se perdem; os eventos continuam).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("sem_gasto_previsto", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                "sem_gasto_realizado", sa.Boolean(), server_default=sa.false(), nullable=False
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.drop_column("sem_gasto_realizado")
        batch_op.drop_column("sem_gasto_previsto")
