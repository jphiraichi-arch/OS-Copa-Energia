"""exclusão lógica de ordens de serviço (lixeira)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-23

Upgrade:
- ordens_servico.excluida_em (data e hora UTC), excluida_por_id (FK usuarios) e
  motivo_exclusao (texto), todos opcionais e vazios nas ordens existentes;
- CHECK exclusao_completa: os três vazios ou os três preenchidos;
- índice em excluida_em (toda consulta filtra excluida_em IS NULL);
- os_eventos.observacao (texto opcional): nota sobre a origem de uma mudança, por exemplo
  a prioridade preenchida a partir da urgência ao iniciar.
Downgrade: remove os_eventos.observacao (as notas se perdem), o índice, o CHECK e as três
colunas. As ordens que estavam na lixeira
voltam a aparecer como ordens comuns (a marca de exclusão se perde); os eventos
EXCLUSAO e RESTAURACAO continuam no histórico.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from osapp.models.tipos import DataHoraUTC

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK = (
    "(excluida_em IS NULL AND excluida_por_id IS NULL AND motivo_exclusao IS NULL)"
    " OR (excluida_em IS NOT NULL AND excluida_por_id IS NOT NULL"
    " AND motivo_exclusao IS NOT NULL)"
)


def upgrade() -> None:
    with op.batch_alter_table("os_eventos", schema=None) as batch_op:
        batch_op.add_column(sa.Column("observacao", sa.Text(), nullable=True))
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.add_column(sa.Column("excluida_em", DataHoraUTC(), nullable=True))
        batch_op.add_column(sa.Column("excluida_por_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("motivo_exclusao", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            op.f("fk_ordens_servico_excluida_por_id_usuarios"),
            "usuarios",
            ["excluida_por_id"],
            ["id"],
        )
        batch_op.create_check_constraint(op.f("ck_ordens_servico_exclusao_completa"), CHECK)
        batch_op.create_index(op.f("ix_ordens_servico_excluida_em"), ["excluida_em"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.drop_index(op.f("ix_ordens_servico_excluida_em"))
        batch_op.drop_constraint(op.f("ck_ordens_servico_exclusao_completa"), type_="check")
        batch_op.drop_constraint(
            op.f("fk_ordens_servico_excluida_por_id_usuarios"), type_="foreignkey"
        )
        batch_op.drop_column("motivo_exclusao")
        batch_op.drop_column("excluida_por_id")
        batch_op.drop_column("excluida_em")
    with op.batch_alter_table("os_eventos", schema=None) as batch_op:
        batch_op.drop_column("observacao")
