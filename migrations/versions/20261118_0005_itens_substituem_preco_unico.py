"""itens de custo substituem o preço único da OS

Para cada OS: o valor previsto vira um item PREVISTO e o realizado (se houver) um item
REALIZADO, na categoria OUTROS, descrição 'Valor total (migrado)', quantidade 1. OS sem
equipamento recebem equipamento_outro 'Não informado'. Depois as colunas de preço único
saem. O downgrade recria as colunas com a soma dos itens.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-18
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

import sqlalchemy as sa
from alembic import op

from osapp.models.tipos import DataHoraUTC, Quantidade

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DESCRICAO_MIGRADA = "Valor total (migrado)"
SEM_EQUIPAMENTO = "Não informado"
log = logging.getLogger("alembic.runtime.migration")

ordens = sa.table(
    "ordens_servico",
    sa.column("id", sa.Integer),
    sa.column("valor_previsto_centavos", sa.BigInteger),
    sa.column("valor_realizado_centavos", sa.BigInteger),
    sa.column("equipamento_id", sa.Integer),
    sa.column("equipamento_outro", sa.String),
)
itens = sa.table(
    "os_itens_custo",
    sa.column("os_id", sa.Integer),
    sa.column("fase", sa.String),
    sa.column("categoria_id", sa.Integer),
    sa.column("descricao", sa.String),
    sa.column("quantidade", Quantidade()),
    sa.column("valor_unitario_centavos", sa.BigInteger),
    sa.column("criado_em", DataHoraUTC()),
    sa.column("atualizado_em", DataHoraUTC()),
)
categorias = sa.table(
    "categorias_custo", sa.column("id", sa.Integer), sa.column("codigo", sa.String)
)


def upgrade() -> None:
    conexao = op.get_bind()
    outros = conexao.execute(
        sa.select(categorias.c.id).where(categorias.c.codigo == "OUTROS")
    ).scalar_one()
    ja_tem = set(conexao.execute(sa.select(itens.c.os_id, itens.c.fase)).all())
    agora = datetime.now(UTC)
    novos = []
    linhas = conexao.execute(
        sa.select(ordens.c.id, ordens.c.valor_previsto_centavos, ordens.c.valor_realizado_centavos)
    ).all()
    for os_id, previsto, realizado in linhas:
        for fase, valor in (("PREVISTO", previsto), ("REALIZADO", realizado)):
            if valor is not None and (os_id, fase) not in ja_tem:
                novos.append(
                    {
                        "os_id": os_id,
                        "fase": fase,
                        "categoria_id": outros,
                        "descricao": DESCRICAO_MIGRADA,
                        "quantidade": Decimal("1.00"),
                        "valor_unitario_centavos": valor,
                        "criado_em": agora,
                        "atualizado_em": agora,
                    }
                )
    if novos:
        conexao.execute(itens.insert(), novos)
    sem_equipamento = conexao.execute(
        ordens.update()
        .where(ordens.c.equipamento_id.is_(None))
        .where(sa.or_(ordens.c.equipamento_outro.is_(None), ordens.c.equipamento_outro == ""))
        .values(equipamento_outro=SEM_EQUIPAMENTO)
    ).rowcount
    log.info(
        "0005: %s OS, %s item(ns) migrado(s), %s OS sem equipamento receberam '%s'.",
        len(linhas),
        len(novos),
        sem_equipamento,
        SEM_EQUIPAMENTO,
    )
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f("ck_ordens_servico_valor_previsto_nao_negativo"), type_="check"
        )
        batch_op.drop_column("valor_realizado_centavos")
        batch_op.drop_column("valor_previsto_centavos")


def downgrade() -> None:
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.add_column(sa.Column("valor_previsto_centavos", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("valor_realizado_centavos", sa.BigInteger(), nullable=True))
    conexao = op.get_bind()
    somas: dict[int, dict[str, int]] = {}
    for os_id, fase, quantidade, valor in conexao.execute(
        sa.select(itens.c.os_id, itens.c.fase, itens.c.quantidade, itens.c.valor_unitario_centavos)
    ).all():
        total = int((Decimal(valor) * quantidade).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        somas.setdefault(os_id, {}).setdefault(fase, 0)
        somas[os_id][fase] += total
    for (os_id,) in conexao.execute(sa.select(ordens.c.id)).all():
        fases = somas.get(os_id, {})
        conexao.execute(
            ordens.update()
            .where(ordens.c.id == os_id)
            .values(
                valor_previsto_centavos=fases.get("PREVISTO", 0),
                valor_realizado_centavos=fases.get("REALIZADO"),
            )
        )
    conexao.execute(itens.delete().where(itens.c.descricao == DESCRICAO_MIGRADA))
    conexao.execute(
        ordens.update()
        .where(ordens.c.equipamento_outro == SEM_EQUIPAMENTO)
        .values(equipamento_outro=None)
    )
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.alter_column(
            "valor_previsto_centavos", existing_type=sa.BigInteger(), nullable=False
        )
        batch_op.create_check_constraint(
            "valor_previsto_nao_negativo", "valor_previsto_centavos >= 0"
        )
