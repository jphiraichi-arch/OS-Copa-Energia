"""'Lembrar de mim por 7 dias': tokens com hash, rotação e revogação (prompt 35)

Revision ID: 0016
Revises: 0015
Create Date: 2026-11-25

Upgrade: cria sessoes_lembradas (id, usuario_id, familia, token_hash único, criado_em,
expira_em, ultimo_uso_em, rotulo_aparelho, revogado_em). Vazia: ninguém fica lembrado.
Downgrade: apaga a tabela. Todos os aparelhos lembrados passam a pedir a senha (o token
guardado no navegador deixa de valer e é apagado na próxima tentativa).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from osapp.models.tipos import DataHoraUTC

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sessoes_lembradas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("familia", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("criado_em", DataHoraUTC(), nullable=False),
        sa.Column("expira_em", DataHoraUTC(), nullable=False),
        sa.Column("ultimo_uso_em", DataHoraUTC(), nullable=True),
        sa.Column("rotulo_aparelho", sa.String(length=60), nullable=False),
        sa.Column("revogado_em", DataHoraUTC(), nullable=True),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], name=op.f("fk_sessoes_lembradas_usuario_id_usuarios")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sessoes_lembradas")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sessoes_lembradas_token_hash")),
    )
    op.create_index(
        op.f("ix_sessoes_lembradas_usuario_id"), "sessoes_lembradas", ["usuario_id"], unique=False
    )
    op.create_index(
        op.f("ix_sessoes_lembradas_familia"), "sessoes_lembradas", ["familia"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_sessoes_lembradas_familia"), table_name="sessoes_lembradas")
    op.drop_index(op.f("ix_sessoes_lembradas_usuario_id"), table_name="sessoes_lembradas")
    op.drop_table("sessoes_lembradas")
