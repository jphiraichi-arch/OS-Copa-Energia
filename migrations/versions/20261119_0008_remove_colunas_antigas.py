"""papel substitui is_admin; instantes novos substituem iniciado_em e concluido_em

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-19

Upgrade:
- copia de novo, para as OS gravadas pelo código antigo depois da 0007:
  aberta_em = criado_em; inicio_execucao_em = iniciado_em; concluida_em = concluido_em;
  e papel = 'admin' onde is_admin ainda for verdadeiro (e o contrário);
- remove usuarios.is_admin, ordens_servico.iniciado_em e ordens_servico.concluido_em.

Downgrade: recria as três colunas a partir de papel e dos instantes novos. OS canceladas
continuam com status CANCELADA, que o código anterior ao prompt 17 não conhece.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from osapp.models.tipos import DataHoraUTC

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ordens():
    return sa.table(
        "ordens_servico",
        sa.column("criado_em", DataHoraUTC()),
        sa.column("aberta_em", DataHoraUTC()),
        sa.column("iniciado_em", DataHoraUTC()),
        sa.column("concluido_em", DataHoraUTC()),
        sa.column("inicio_execucao_em", DataHoraUTC()),
        sa.column("concluida_em", DataHoraUTC()),
    )


def _usuarios():
    return sa.table("usuarios", sa.column("papel", sa.String), sa.column("is_admin", sa.Boolean))


def upgrade() -> None:
    conexao = op.get_bind()
    ordens, usuarios = _ordens(), _usuarios()
    # O código antigo gravava só iniciado_em/concluido_em e deixava aberta_em com o padrão
    # do banco (o instante do INSERT): a abertura verdadeira é criado_em.
    conexao.execute(
        ordens.update().values(
            aberta_em=ordens.c.criado_em,
            inicio_execucao_em=ordens.c.iniciado_em,
            concluida_em=ordens.c.concluido_em,
        )
    )
    conexao.execute(usuarios.update().where(usuarios.c.is_admin == sa.true()).values(papel="admin"))
    conexao.execute(
        usuarios.update()
        .where(usuarios.c.is_admin == sa.false(), usuarios.c.papel == "admin")
        .values(papel="manutencao")
    )
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.drop_column("concluido_em")
        batch_op.drop_column("iniciado_em")
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_column("is_admin")


def downgrade() -> None:
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.add_column(sa.Column("iniciado_em", DataHoraUTC(), nullable=True))
        batch_op.add_column(sa.Column("concluido_em", DataHoraUTC(), nullable=True))
    conexao = op.get_bind()
    ordens, usuarios = _ordens(), _usuarios()
    conexao.execute(usuarios.update().where(usuarios.c.papel == "admin").values(is_admin=True))
    conexao.execute(
        ordens.update().values(
            iniciado_em=ordens.c.inicio_execucao_em, concluido_em=ordens.c.concluida_em
        )
    )
