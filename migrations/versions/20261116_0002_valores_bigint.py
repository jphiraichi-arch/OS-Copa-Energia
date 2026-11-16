"""valores em centavos como BIGINT

O limite de negócio (9.999.999.999 centavos) não cabe no INTEGER de 32 bits do PostgreSQL.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUNAS = (("valor_previsto_centavos", False), ("valor_realizado_centavos", True))


def upgrade() -> None:
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        for coluna, anulavel in COLUNAS:
            batch_op.alter_column(
                coluna,
                existing_type=sa.Integer(),
                type_=sa.BigInteger(),
                existing_nullable=anulavel,
            )


def downgrade() -> None:
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        for coluna, anulavel in COLUNAS:
            batch_op.alter_column(
                coluna,
                existing_type=sa.BigInteger(),
                type_=sa.Integer(),
                existing_nullable=anulavel,
            )
