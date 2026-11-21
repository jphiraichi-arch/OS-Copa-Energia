"""remove equipamentos; texto de busca normalizado em ordens e itens

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-21

Upgrade:
- preserva o equipamento (decisão de 21/11/2026): a OS com equipamento_id ou
  equipamento_outro recebe no fim da descricao a linha "Equipamento (legado): <nome>"
  (o nome do cadastro; sem cadastro, o texto livre). O marcador 'Não informado', que a
  migração 0005 gravou nas OS antigas sem equipamento, não é copiado;
- ordens_servico.busca_texto e os_itens_custo.busca_texto (texto, padrão ''), preenchidos
  aqui para as linhas existentes com a cópia congelada de normalizar_busca abaixo (o app
  pode mudar a dele depois; esta migração continua igual);
- remove a chave estrangeira e as colunas ordens_servico.equipamento_id e
  equipamento_outro, e a tabela equipamentos (com codigo_sap). numero_sap fica.
Antes de aplicar em produção: `python -m osapp.cli exportar-equipamentos ARQUIVO.csv`.

Downgrade: recria a tabela equipamentos e as duas colunas, VAZIAS. O vínculo da OS com
o equipamento NÃO volta: o cadastro e as colunas ficam vazios e a linha
"Equipamento (legado): ..." continua na descricao (o downgrade não mexe nela). As
colunas busca_texto saem.
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


ROTULO_LEGADO = "Equipamento (legado): "
SEM_EQUIPAMENTO_0005 = "Não informado"  # marcador da migração 0005, não é um equipamento


def _com_equipamento(descricao, nome_cadastro, texto_livre):
    """Descrição com a linha do equipamento no fim, ou a mesma descrição."""
    outro = (texto_livre or "").strip()
    nome = (nome_cadastro or "").strip() or (outro if outro != SEM_EQUIPAMENTO_0005 else "")
    if not nome:
        return descricao
    base = (descricao or "").rstrip()
    return f"{base}\n\n{ROTULO_LEGADO}{nome}" if base else f"{ROTULO_LEGADO}{nome}"


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
        sa.column("equipamento_id", sa.Integer),
        sa.column("equipamento_outro", sa.String),
    )
    cadastro = sa.table("equipamentos", sa.column("id", sa.Integer), sa.column("nome", sa.String))
    itens = sa.table(
        "os_itens_custo",
        sa.column("id", sa.Integer),
        sa.column("descricao", sa.String),
        sa.column("busca_texto", sa.Text),
    )
    consulta = sa.select(
        ordens.c.id,
        ordens.c.titulo,
        ordens.c.descricao,
        cadastro.c.nome,
        ordens.c.equipamento_outro,
    ).select_from(ordens.outerjoin(cadastro, ordens.c.equipamento_id == cadastro.c.id))
    for os_id, titulo, descricao, nome, outro in conexao.execute(consulta).all():
        nova = _com_equipamento(descricao, nome, outro)
        conexao.execute(
            ordens.update()
            .where(ordens.c.id == os_id)
            .values(descricao=nova, busca_texto=_normalizar(f"{titulo or ''} {nova or ''}"))
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
