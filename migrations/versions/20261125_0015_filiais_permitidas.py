"""filiais permitidas por usuário (prompts 28 e 34)

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-25

Upgrade: cria usuario_filiais (usuario_id, filial_id; par único) e dá a cada usuário a
própria filial atual (usuarios.filial_id, que passa a ser a 'filial padrão'). Ninguém
ganha nem perde acesso.
Downgrade: apaga usuario_filiais. As filiais extras se perdem; cada usuário fica só com
a filial padrão (usuarios.filial_id não muda).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usuario_filiais",
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("filial_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["filial_id"], ["filiais.id"], name=op.f("fk_usuario_filiais_filial_id_filiais")
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], name=op.f("fk_usuario_filiais_usuario_id_usuarios")
        ),
        sa.PrimaryKeyConstraint("usuario_id", "filial_id", name=op.f("pk_usuario_filiais")),
    )
    usuarios = sa.table("usuarios", sa.column("id", sa.Integer), sa.column("filial_id", sa.Integer))
    destino = sa.table(
        "usuario_filiais", sa.column("usuario_id", sa.Integer), sa.column("filial_id", sa.Integer)
    )
    op.execute(
        destino.insert().from_select(
            ["usuario_id", "filial_id"], sa.select(usuarios.c.id, usuarios.c.filial_id)
        )
    )


def downgrade() -> None:
    op.drop_table("usuario_filiais")
