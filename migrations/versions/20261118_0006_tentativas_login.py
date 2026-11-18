"""tentativas_login (atraso progressivo) substitui o bloqueio em usuarios

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-18

Cria a tabela tentativas_login e remove usuarios.tentativas_falhas e
usuarios.bloqueado_ate (o bloqueio fixo de 15 minutos deixa de existir). Os contadores
antigos não são migrados: estão em texto de login/usuário, e a nova tabela guarda só HMAC.
O downgrade recria as duas colunas zeradas e apaga a tabela.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from osapp.models.tipos import DataHoraUTC

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tentativas_login",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chave", sa.String(length=64), nullable=False),
        sa.Column("tipo", sa.String(length=5), nullable=False),
        sa.Column("falhas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("proximo_permitido_em", DataHoraUTC(), nullable=True),
        sa.Column("atualizado_em", DataHoraUTC(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tentativas_login")),
        sa.UniqueConstraint("tipo", "chave", name=op.f("uq_tentativas_login_tipo")),
    )
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_column("bloqueado_ate")
        batch_op.drop_column("tentativas_falhas")


def downgrade() -> None:
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("tentativas_falhas", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(sa.Column("bloqueado_ate", DataHoraUTC(), nullable=True))
    op.drop_table("tentativas_login")
