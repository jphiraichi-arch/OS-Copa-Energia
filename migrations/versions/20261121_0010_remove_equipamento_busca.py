"""remove equipamentos; texto de busca normalizado em ordens e itens

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-21

Upgrade:
- ordens_servico.busca_texto e os_itens_custo.busca_texto (texto, padrão ''), preenchidos
  aqui para as linhas existentes com a cópia congelada de normalizar_busca abaixo (o app
  pode mudar a dele depois; esta migração continua igual);
- remove a chave estrangeira e as colunas ordens_servico.equipamento_id e
  equipamento_outro, e a tabela equipamentos (com codigo_sap). numero_sap fica.
Antes de aplicar em produção: `python -m osapp.cli exportar-equipamentos ARQUIVO.csv`.

Downgrade: recria a tabela equipamentos e as duas colunas, VAZIAS. Os equipamentos não
voltam (a fonte é o CSV exportado antes). As colunas busca_texto saem.
"""

import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalizar(texto):
    """Cópia congelada de osapp.busca.normalizar_busca (21/11/2026)."""
    if not texto:
        return ""
    decomposto = unicodedata.normalize("NFKD", str(texto))
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return " ".join(sem_acento.casefold().split())


def upgrade() -> None:
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.add_column(sa.Column("busca_texto", sa.Text(), server_default="", nullable=False))
    with op.batch_alter_table("os_itens_custo", schema=None) as batch_op:
        batch_op.add_column(sa.Column("busca_texto", sa.Text(), server_default="", nullable=False))

    conexao = op.get_bind()
    ordens = sa.table(
        "ordens_servico",
        sa.column("id", sa.Integer),
        sa.column("titulo", sa.String),
        sa.column("descricao", sa.Text),
        sa.column("busca_texto", sa.Text),
    )
    itens = sa.table(
        "os_itens_custo",
        sa.column("id", sa.Integer),
        sa.column("descricao", sa.String),
        sa.column("busca_texto", sa.Text),
    )
    for os_id, titulo, descricao in conexao.execute(
        sa.select(ordens.c.id, ordens.c.titulo, ordens.c.descricao)
    ).all():
        conexao.execute(
            ordens.update()
            .where(ordens.c.id == os_id)
            .values(busca_texto=_normalizar(f"{titulo or ''} {descricao or ''}"))
        )
    for item_id, descricao in conexao.execute(sa.select(itens.c.id, itens.c.descricao)).all():
        conexao.execute(
            itens.update().where(itens.c.id == item_id).values(busca_texto=_normalizar(descricao))
        )

    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_ordens_servico_equipamento_id_equipamentos", type_="foreignkey"
        )
        batch_op.drop_column("equipamento_outro")
        batch_op.drop_column("equipamento_id")
    op.drop_table("equipamentos")


def downgrade() -> None:
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
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.add_column(sa.Column("equipamento_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("equipamento_outro", sa.String(length=120), nullable=True))
        batch_op.create_foreign_key(
            "fk_ordens_servico_equipamento_id_equipamentos",
            "equipamentos",
            ["equipamento_id"],
            ["id"],
        )
        batch_op.drop_column("busca_texto")
    with op.batch_alter_table("os_itens_custo", schema=None) as batch_op:
        batch_op.drop_column("busca_texto")
