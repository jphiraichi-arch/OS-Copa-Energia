"""visualizações de OS pela manutenção (prompt 42)

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-25

Upgrade: os_visualizacoes (id, os_id FK, usuario_id FK, primeira_visualizacao_em,
ultima_visualizacao_em; par (os_id, usuario_id) único; índice em os_id). Vazia: nenhuma
OS existente aparece como visualizada.
Downgrade: apaga a tabela. As visualizações se perdem; os eventos VISUALIZACAO continuam
no histórico (como texto).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from osapp.models.tipos import DataHoraUTC

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "os_visualizacoes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("os_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("primeira_visualizacao_em", DataHoraUTC(), nullable=False),
        sa.Column("ultima_visualizacao_em", DataHoraUTC(), nullable=False),
        sa.ForeignKeyConstraint(
            ["os_id"], ["ordens_servico.id"], name=op.f("fk_os_visualizacoes_os_id_ordens_servico")
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], name=op.f("fk_os_visualizacoes_usuario_id_usuarios")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_os_visualizacoes")),
        sa.UniqueConstraint("os_id", "usuario_id", name=op.f("uq_os_visualizacoes_os_id")),
    )
    op.create_index(op.f("ix_os_visualizacoes_os_id"), "os_visualizacoes", ["os_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_os_visualizacoes_os_id"), table_name="os_visualizacoes")
    op.drop_table("os_visualizacoes")
