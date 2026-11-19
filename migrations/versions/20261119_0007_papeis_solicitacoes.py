"""papéis, tipos de manutenção, solicitações e instantes de status

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-19

- usuarios.papel ('usuario' | 'manutencao' | 'admin'); dados: is_admin -> 'admin', os
  demais -> 'manutencao'. is_admin continua (o código implantado ainda o lê).
- tipos_manutencao, com CORRETIVA, PREVENTIVA, PREDITIVA, MELHORIA e OUTRO.
- ordens_servico: origem, urgencia, prioridade, tipo_id, nota_conclusao, aberta_em,
  inicio_execucao_em, concluida_em, cancelada_em, cancelada_por_id; dados: origem
  'manutencao', aberta_em = criado_em, inicio_execucao_em = iniciado_em,
  concluida_em = concluido_em. iniciado_em e concluido_em continuam.
- tempo_previsto_minutos passa a aceitar NULL (o CHECK vale só quando preenchido).
- CHECKs de linha do tempo. Antes de criá-los, a migração procura linhas que os violariam
  e, se houver, para com a lista dos números (nada é alterado: a transação é desfeita).
- Índices (filial_id, origem, aberta_em) e (status).

Downgrade: remove tudo isso. tempo_previsto_minutos volta a NOT NULL; OS sem tempo
previsto (só possíveis depois do prompt 17) recebem 1 minuto, e a quantidade vai para o log.
"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from osapp.models.tipos import DataHoraUTC

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger("alembic.runtime.migration")

TIPOS = [
    {"codigo": "CORRETIVA", "nome": "Corretiva", "ordem": 1, "ativo": True},
    {"codigo": "PREVENTIVA", "nome": "Preventiva", "ordem": 2, "ativo": True},
    {"codigo": "PREDITIVA", "nome": "Preditiva", "ordem": 3, "ativo": True},
    {"codigo": "MELHORIA", "nome": "Melhoria", "ordem": 4, "ativo": True},
    {"codigo": "OUTRO", "nome": "Outro", "ordem": 5, "ativo": True},
]

NIVEIS = "('baixa', 'media', 'alta', 'emergencial')"
CHECKS_LINHA_DO_TEMPO = [
    ("inicio_apos_abertura", "inicio_execucao_em >= aberta_em"),
    ("conclusao_apos_inicio", "concluida_em >= inicio_execucao_em"),
    ("cancelamento_apos_abertura", "cancelada_em >= aberta_em"),
    ("concluida_ou_cancelada", "concluida_em IS NULL OR cancelada_em IS NULL"),
]
CHECKS_VALORES = [
    ("origem_valida", "origem IN ('solicitacao', 'manutencao')"),
    ("urgencia_valida", f"urgencia IN {NIVEIS}"),
    ("prioridade_valida", f"prioridade IN {NIVEIS}"),
]


def _tabela_ordens():
    return sa.table(
        "ordens_servico",
        sa.column("id", sa.Integer),
        sa.column("numero", sa.String),
        sa.column("criado_em", DataHoraUTC()),
        sa.column("iniciado_em", DataHoraUTC()),
        sa.column("concluido_em", DataHoraUTC()),
        sa.column("aberta_em", DataHoraUTC()),
        sa.column("inicio_execucao_em", DataHoraUTC()),
        sa.column("concluida_em", DataHoraUTC()),
        sa.column("cancelada_em", DataHoraUTC()),
        sa.column("tempo_previsto_minutos", sa.Integer),
    )


def upgrade() -> None:
    conexao = op.get_bind()

    tipos = op.create_table(
        "tipos_manutencao",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=30), nullable=False),
        sa.Column("nome", sa.String(length=60), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tipos_manutencao")),
        sa.UniqueConstraint("codigo", name=op.f("uq_tipos_manutencao_codigo")),
    )
    op.bulk_insert(tipos, TIPOS)

    # --- usuarios.papel --------------------------------------------------------------
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("papel", sa.String(length=20), server_default="manutencao", nullable=False)
        )
    usuarios = sa.table("usuarios", sa.column("papel", sa.String), sa.column("is_admin"))
    conexao.execute(usuarios.update().where(usuarios.c.is_admin == sa.true()).values(papel="admin"))
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.create_check_constraint(
            op.f("ck_usuarios_papel_valido"), "papel IN ('usuario', 'manutencao', 'admin')"
        )

    # --- ordens_servico: colunas novas -----------------------------------------------
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("origem", sa.String(length=20), server_default="manutencao", nullable=False)
        )
        batch_op.add_column(sa.Column("urgencia", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("prioridade", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("tipo_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("nota_conclusao", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("aberta_em", DataHoraUTC(), nullable=True))
        batch_op.add_column(sa.Column("inicio_execucao_em", DataHoraUTC(), nullable=True))
        batch_op.add_column(sa.Column("concluida_em", DataHoraUTC(), nullable=True))
        batch_op.add_column(sa.Column("cancelada_em", DataHoraUTC(), nullable=True))
        batch_op.add_column(sa.Column("cancelada_por_id", sa.Integer(), nullable=True))
        batch_op.alter_column("tempo_previsto_minutos", existing_type=sa.Integer(), nullable=True)

    ordens = _tabela_ordens()
    conexao.execute(
        ordens.update().values(
            aberta_em=ordens.c.criado_em,
            inicio_execucao_em=ordens.c.iniciado_em,
            concluida_em=ordens.c.concluido_em,
        )
    )

    # Linhas que violariam os CHECKs de linha do tempo: listar e parar.
    c = ordens.c
    regras = {
        "inicio_apos_abertura": c.inicio_execucao_em < c.aberta_em,
        "conclusao_apos_inicio": c.concluida_em < c.inicio_execucao_em,
        "cancelamento_apos_abertura": c.cancelada_em < c.aberta_em,
        "concluida_ou_cancelada": sa.and_(c.concluida_em.is_not(None), c.cancelada_em.is_not(None)),
    }
    violacoes = []
    for nome, condicao in regras.items():
        numeros = conexao.execute(sa.select(c.numero).where(condicao)).scalars().all()
        violacoes += [f"{nome}: {numero}" for numero in numeros]
    if violacoes:
        raise RuntimeError(
            "Migração 0007 interrompida: OS com linha do tempo impossível (nada foi "
            "alterado): " + "; ".join(violacoes)
        )

    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.alter_column(
            "aberta_em",
            existing_type=DataHoraUTC(),
            nullable=False,
            server_default=sa.func.now(),
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_ordens_servico_tipo_id_tipos_manutencao"),
            "tipos_manutencao",
            ["tipo_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_ordens_servico_cancelada_por_id_usuarios"),
            "usuarios",
            ["cancelada_por_id"],
            ["id"],
        )
        for nome, condicao in CHECKS_VALORES + CHECKS_LINHA_DO_TEMPO:
            batch_op.create_check_constraint(op.f(f"ck_ordens_servico_{nome}"), condicao)
        batch_op.create_index(
            "ix_ordens_servico_filial_id_origem_aberta_em",
            ["filial_id", "origem", "aberta_em"],
            unique=False,
        )
        batch_op.create_index("ix_ordens_servico_status", ["status"], unique=False)


def downgrade() -> None:
    conexao = op.get_bind()
    ordens = _tabela_ordens()
    sem_tempo = conexao.execute(
        ordens.update()
        .where(ordens.c.tempo_previsto_minutos.is_(None))
        .values(tempo_previsto_minutos=1)
    ).rowcount
    if sem_tempo:
        logger.warning("Downgrade 0007: %s OS sem tempo previsto receberam 1 minuto.", sem_tempo)

    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.drop_index("ix_ordens_servico_status")
        batch_op.drop_index("ix_ordens_servico_filial_id_origem_aberta_em")
        for nome, _condicao in CHECKS_VALORES + CHECKS_LINHA_DO_TEMPO:
            batch_op.drop_constraint(op.f(f"ck_ordens_servico_{nome}"), type_="check")
        batch_op.drop_constraint(
            batch_op.f("fk_ordens_servico_cancelada_por_id_usuarios"), type_="foreignkey"
        )
        batch_op.drop_constraint(
            batch_op.f("fk_ordens_servico_tipo_id_tipos_manutencao"), type_="foreignkey"
        )
        batch_op.alter_column("tempo_previsto_minutos", existing_type=sa.Integer(), nullable=False)
        for coluna in (
            "cancelada_por_id",
            "cancelada_em",
            "concluida_em",
            "inicio_execucao_em",
            "aberta_em",
            "nota_conclusao",
            "tipo_id",
            "prioridade",
            "urgencia",
            "origem",
        ):
            batch_op.drop_column(coluna)

    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_usuarios_papel_valido"), type_="check")
        batch_op.drop_column("papel")

    op.drop_table("tipos_manutencao")
