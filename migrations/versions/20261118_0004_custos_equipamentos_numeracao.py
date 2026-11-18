"""itens de custo, categorias, equipamentos, sequência de numeração, campos SAP

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from osapp.models.tipos import DataHoraUTC, Quantidade

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORIAS = [
    {"codigo": "MAO_DE_OBRA", "nome": "Mão de obra", "ordem": 1, "ativo": True},
    {"codigo": "PECAS_MATERIAIS", "nome": "Peças/materiais", "ordem": 2, "ativo": True},
    {"codigo": "SERVICOS_TERCEIROS", "nome": "Serviços de terceiros", "ordem": 3, "ativo": True},
    {"codigo": "OUTROS", "nome": "Outros", "ordem": 4, "ativo": True},
]


def upgrade() -> None:
    categorias = op.create_table(
        "categorias_custo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=30), nullable=False),
        sa.Column("nome", sa.String(length=60), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categorias_custo")),
        sa.UniqueConstraint("codigo", name=op.f("uq_categorias_custo_codigo")),
    )
    op.bulk_insert(categorias, CATEGORIAS)

    op.create_table(
        "equipamentos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filial_id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=120), nullable=False),
        sa.Column("codigo_sap", sa.String(length=40), nullable=True),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(
            ["filial_id"], ["filiais.id"], name=op.f("fk_equipamentos_filial_id_filiais")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipamentos")),
    )

    op.create_table(
        "os_sequencias",
        sa.Column("filial_id", sa.Integer(), nullable=False),
        sa.Column("ano", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("ultimo_numero", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["filial_id"], ["filiais.id"], name=op.f("fk_os_sequencias_filial_id_filiais")
        ),
        sa.PrimaryKeyConstraint("filial_id", "ano", name=op.f("pk_os_sequencias")),
    )

    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.alter_column(
            "numero",
            existing_type=sa.String(length=20),
            type_=sa.String(length=30),
            existing_nullable=False,
        )
        batch_op.add_column(sa.Column("numero_sap", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("equipamento_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("equipamento_outro", sa.String(length=120), nullable=True))
        batch_op.create_index("ix_ordens_servico_numero_sap", ["numero_sap"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_ordens_servico_equipamento_id_equipamentos"),
            "equipamentos",
            ["equipamento_id"],
            ["id"],
        )

    op.create_table(
        "os_itens_custo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("os_id", sa.Integer(), nullable=False),
        sa.Column("fase", sa.String(length=10), nullable=False),
        sa.Column("categoria_id", sa.Integer(), nullable=False),
        sa.Column("descricao", sa.String(length=200), nullable=False),
        sa.Column("quantidade", Quantidade(), nullable=False),
        sa.Column("valor_unitario_centavos", sa.BigInteger(), nullable=False),
        sa.Column("criado_em", DataHoraUTC(), nullable=False),
        sa.Column("atualizado_em", DataHoraUTC(), nullable=False),
        sa.CheckConstraint(
            "fase IN ('PREVISTO', 'REALIZADO')", name=op.f("ck_os_itens_custo_fase_valida")
        ),
        sa.CheckConstraint("quantidade > 0", name=op.f("ck_os_itens_custo_quantidade_positiva")),
        sa.CheckConstraint(
            "valor_unitario_centavos >= 0",
            name=op.f("ck_os_itens_custo_valor_unitario_nao_negativo"),
        ),
        sa.ForeignKeyConstraint(
            ["categoria_id"],
            ["categorias_custo.id"],
            name=op.f("fk_os_itens_custo_categoria_id_categorias_custo"),
        ),
        sa.ForeignKeyConstraint(
            ["os_id"],
            ["ordens_servico.id"],
            name=op.f("fk_os_itens_custo_os_id_ordens_servico"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_os_itens_custo")),
    )
    with op.batch_alter_table("os_itens_custo", schema=None) as batch_op:
        batch_op.create_index("ix_os_itens_custo_os_id_fase", ["os_id", "fase"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("os_itens_custo", schema=None) as batch_op:
        batch_op.drop_index("ix_os_itens_custo_os_id_fase")
    op.drop_table("os_itens_custo")

    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_ordens_servico_equipamento_id_equipamentos"), type_="foreignkey"
        )
        batch_op.drop_index("ix_ordens_servico_numero_sap")
        batch_op.drop_column("equipamento_outro")
        batch_op.drop_column("equipamento_id")
        batch_op.drop_column("numero_sap")
        batch_op.alter_column(
            "numero",
            existing_type=sa.String(length=30),
            type_=sa.String(length=20),
            existing_nullable=False,
        )

    op.drop_table("os_sequencias")
    op.drop_table("equipamentos")
    op.drop_table("categorias_custo")
