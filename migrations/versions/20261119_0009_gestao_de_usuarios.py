"""gestão de usuários: troca obrigatória de senha, versão e histórico

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-19

- usuarios.deve_trocar_senha (padrão falso) e usuarios.versao (padrão 1, trava otimista);
- tabela usuarios_eventos (admin_id, usuario_id, data_hora, campo, valor_antigo,
  valor_novo), só de inserção.
Downgrade: remove a tabela e as duas colunas (o histórico de usuários se perde).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from osapp.models.tipos import DataHoraUTC

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("deve_trocar_senha", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(sa.Column("versao", sa.Integer(), server_default="1", nullable=False))
    op.create_table(
        "usuarios_eventos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("admin_id", sa.Integer(), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("data_hora", DataHoraUTC(), nullable=False),
        sa.Column("campo", sa.String(length=40), nullable=False),
        sa.Column("valor_antigo", sa.String(length=200), nullable=True),
        sa.Column("valor_novo", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ["admin_id"], ["usuarios.id"], name=op.f("fk_usuarios_eventos_admin_id_usuarios")
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], name=op.f("fk_usuarios_eventos_usuario_id_usuarios")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usuarios_eventos")),
    )
    with op.batch_alter_table("usuarios_eventos", schema=None) as batch_op:
        batch_op.create_index("ix_usuarios_eventos_usuario_id", ["usuario_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("usuarios_eventos", schema=None) as batch_op:
        batch_op.drop_index("ix_usuarios_eventos_usuario_id")
    op.drop_table("usuarios_eventos")
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_column("versao")
        batch_op.drop_column("deve_trocar_senha")
