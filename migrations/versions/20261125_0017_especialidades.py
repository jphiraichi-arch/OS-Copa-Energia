"""especialidades nas ordens e nos usuários (prompt 37)

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-25

Upgrade:
- especialidades (codigo único, nome, ordem, ativo) com MECANICA 'Mecânica', ELETRICA
  'Elétrica', PREDIAL 'Predial/civil' e UTILIDADES 'Utilidades';
- ordens_servico.especialidade_id (FK, opcional): as ordens existentes ficam vazias
  ('Não informada' no relatório);
- usuario_especialidades (usuario_id, especialidade_id; par único).
Downgrade: apaga usuario_especialidades, a coluna e a tabela. As especialidades
escolhidas nas ordens e nos usuários se perdem; os eventos EDICAO com o campo
especialidade_id continuam no histórico (com o nome, em texto).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INICIAIS = (
    ("MECANICA", "Mecânica", 1),
    ("ELETRICA", "Elétrica", 2),
    ("PREDIAL", "Predial/civil", 3),
    ("UTILIDADES", "Utilidades", 4),
)


def upgrade() -> None:
    tabela = op.create_table(
        "especialidades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=30), nullable=False),
        sa.Column("nome", sa.String(length=60), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_especialidades")),
        sa.UniqueConstraint("codigo", name=op.f("uq_especialidades_codigo")),
    )
    op.bulk_insert(tabela, [{"codigo": c, "nome": n, "ordem": o} for c, n, o in INICIAIS])
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.add_column(sa.Column("especialidade_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            op.f("fk_ordens_servico_especialidade_id_especialidades"),
            "especialidades",
            ["especialidade_id"],
            ["id"],
        )
    op.create_table(
        "usuario_especialidades",
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("especialidade_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["especialidade_id"],
            ["especialidades.id"],
            name=op.f("fk_usuario_especialidades_especialidade_id_especialidades"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_usuario_especialidades_usuario_id_usuarios"),
        ),
        sa.PrimaryKeyConstraint(
            "usuario_id", "especialidade_id", name=op.f("pk_usuario_especialidades")
        ),
    )


def downgrade() -> None:
    op.drop_table("usuario_especialidades")
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f("fk_ordens_servico_especialidade_id_especialidades"), type_="foreignkey"
        )
        batch_op.drop_column("especialidade_id")
    op.drop_table("especialidades")
