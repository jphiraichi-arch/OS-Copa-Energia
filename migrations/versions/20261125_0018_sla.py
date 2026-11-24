"""SLA: alvos por filial e urgência e prazos nas ordens (prompt 38)

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-25

Upgrade:
- sla_alvos (filial_id, urgencia, prazo_inicio_min, prazo_solucao_min; par único; prazos
  > 0) com os padrões para cada filial: emergencial 1 h / 8 h, alta 4 h / 2 dias, média
  1 dia / 5 dias, baixa 3 dias / 15 dias (dia = 24 horas de relógio);
- ordens_servico.prazo_inicio_em e prazo_solucao_em (opcionais), preenchidos nas
  solicitações existentes (com urgência e aberta_em) a partir dos padrões. Ordens sem
  urgência (criadas pela manutenção) ficam sem prazo.
Downgrade: apaga as duas colunas e a tabela. Os prazos gravados se perdem (são refeitos
por esta mesma migração se ela for aplicada de novo, com os padrões).
"""

from collections.abc import Sequence
from datetime import timedelta

import sqlalchemy as sa
from alembic import op

from osapp.models.tipos import DataHoraUTC

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# urgência -> (início, solução) em minutos. Cópia fixa (a migração não muda com o código).
PADROES = {
    "emergencial": (60, 8 * 60),
    "alta": (4 * 60, 2 * 1440),
    "media": (1440, 5 * 1440),
    "baixa": (3 * 1440, 15 * 1440),
}


def upgrade() -> None:
    alvos = op.create_table(
        "sla_alvos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filial_id", sa.Integer(), nullable=False),
        sa.Column("urgencia", sa.String(length=12), nullable=False),
        sa.Column("prazo_inicio_min", sa.Integer(), nullable=False),
        sa.Column("prazo_solucao_min", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "urgencia IN ('baixa', 'media', 'alta', 'emergencial')",
            name=op.f("ck_sla_alvos_urgencia_valida"),
        ),
        sa.CheckConstraint(
            "prazo_inicio_min > 0 AND prazo_solucao_min > 0",
            name=op.f("ck_sla_alvos_prazos_positivos"),
        ),
        sa.ForeignKeyConstraint(
            ["filial_id"], ["filiais.id"], name=op.f("fk_sla_alvos_filial_id_filiais")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sla_alvos")),
        sa.UniqueConstraint("filial_id", "urgencia", name=op.f("uq_sla_alvos_filial_id")),
    )
    conexao = op.get_bind()
    filiais = sa.table("filiais", sa.column("id", sa.Integer))
    ids = [linha[0] for linha in conexao.execute(sa.select(filiais.c.id))]
    linhas = [
        {"filial_id": f, "urgencia": u, "prazo_inicio_min": i, "prazo_solucao_min": s}
        for f in ids
        for u, (i, s) in PADROES.items()
    ]
    if linhas:
        op.bulk_insert(alvos, linhas)

    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.add_column(sa.Column("prazo_inicio_em", DataHoraUTC(), nullable=True))
        batch_op.add_column(sa.Column("prazo_solucao_em", DataHoraUTC(), nullable=True))

    ordens = sa.table(
        "ordens_servico",
        sa.column("id", sa.Integer),
        sa.column("urgencia", sa.String),
        sa.column("aberta_em", DataHoraUTC()),
        sa.column("origem", sa.String),
        sa.column("prazo_inicio_em", DataHoraUTC()),
        sa.column("prazo_solucao_em", DataHoraUTC()),
    )
    existentes = conexao.execute(
        sa.select(ordens.c.id, ordens.c.urgencia, ordens.c.aberta_em).where(
            ordens.c.origem == "solicitacao",
            ordens.c.urgencia.is_not(None),
            ordens.c.aberta_em.is_not(None),
        )
    ).all()
    for os_id, urgencia, aberta_em in existentes:
        inicio, solucao = PADROES.get(urgencia, (None, None))
        if inicio is None:
            continue
        conexao.execute(
            ordens.update()
            .where(ordens.c.id == os_id)
            .values(
                prazo_inicio_em=aberta_em + timedelta(minutes=inicio),
                prazo_solucao_em=aberta_em + timedelta(minutes=solucao),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.drop_column("prazo_solucao_em")
        batch_op.drop_column("prazo_inicio_em")
    op.drop_table("sla_alvos")
