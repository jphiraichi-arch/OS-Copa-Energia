"""tabelas iniciais

Revision ID: 0001
Revises: -
Create Date: 2026-11-16 03:39:09.510209
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from osapp.models.tipos import DataHoraUTC

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "filiais",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(length=10), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_filiais")),
        sa.UniqueConstraint("codigo", name=op.f("uq_filiais_codigo")),
    )
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("login", sa.String(length=50), nullable=False),
        sa.Column("senha_hash", sa.String(length=255), nullable=False),
        sa.Column("filial_id", sa.Integer(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("tentativas_falhas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bloqueado_ate", DataHoraUTC(), nullable=True),
        sa.ForeignKeyConstraint(
            ["filial_id"], ["filiais.id"], name=op.f("fk_usuarios_filial_id_filiais")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usuarios")),
        sa.UniqueConstraint("login", name=op.f("uq_usuarios_login")),
    )
    op.create_table(
        "ordens_servico",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("numero", sa.String(length=20), nullable=False),
        sa.Column("filial_id", sa.Integer(), nullable=False),
        sa.Column("criado_por_id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(length=120), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("valor_previsto_centavos", sa.Integer(), nullable=False),
        sa.Column("tempo_previsto_minutos", sa.Integer(), nullable=False),
        sa.Column("valor_realizado_centavos", sa.Integer(), nullable=True),
        sa.Column("inicio_realizado", DataHoraUTC(), nullable=True),
        sa.Column("fim_realizado", DataHoraUTC(), nullable=True),
        sa.Column("descricao_realizado", sa.Text(), nullable=True),
        sa.Column("executor_id", sa.Integer(), nullable=True),
        sa.Column("iniciado_em", DataHoraUTC(), nullable=True),
        sa.Column("concluido_por_id", sa.Integer(), nullable=True),
        sa.Column("concluido_em", DataHoraUTC(), nullable=True),
        sa.Column("criado_em", DataHoraUTC(), nullable=False),
        sa.Column("atualizado_em", DataHoraUTC(), nullable=False),
        sa.Column("versao", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "tempo_previsto_minutos > 0", name=op.f("ck_ordens_servico_tempo_previsto_positivo")
        ),
        sa.CheckConstraint(
            "valor_previsto_centavos >= 0",
            name=op.f("ck_ordens_servico_valor_previsto_nao_negativo"),
        ),
        sa.ForeignKeyConstraint(
            ["concluido_por_id"],
            ["usuarios.id"],
            name=op.f("fk_ordens_servico_concluido_por_id_usuarios"),
        ),
        sa.ForeignKeyConstraint(
            ["criado_por_id"],
            ["usuarios.id"],
            name=op.f("fk_ordens_servico_criado_por_id_usuarios"),
        ),
        sa.ForeignKeyConstraint(
            ["executor_id"], ["usuarios.id"], name=op.f("fk_ordens_servico_executor_id_usuarios")
        ),
        sa.ForeignKeyConstraint(
            ["filial_id"], ["filiais.id"], name=op.f("fk_ordens_servico_filial_id_filiais")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ordens_servico")),
        sa.UniqueConstraint("numero", name=op.f("uq_ordens_servico_numero")),
    )
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.create_index("ix_ordens_servico_criado_em", ["criado_em"], unique=False)
        batch_op.create_index(
            "ix_ordens_servico_filial_id_status", ["filial_id", "status"], unique=False
        )

    op.create_table(
        "os_eventos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("os_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("data_hora", DataHoraUTC(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("campo", sa.String(length=50), nullable=True),
        sa.Column("valor_antigo", sa.Text(), nullable=True),
        sa.Column("valor_novo", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["os_id"], ["ordens_servico.id"], name=op.f("fk_os_eventos_os_id_ordens_servico")
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], name=op.f("fk_os_eventos_usuario_id_usuarios")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_os_eventos")),
    )
    with op.batch_alter_table("os_eventos", schema=None) as batch_op:
        batch_op.create_index("ix_os_eventos_os_id", ["os_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("os_eventos", schema=None) as batch_op:
        batch_op.drop_index("ix_os_eventos_os_id")

    op.drop_table("os_eventos")
    with op.batch_alter_table("ordens_servico", schema=None) as batch_op:
        batch_op.drop_index("ix_ordens_servico_filial_id_status")
        batch_op.drop_index("ix_ordens_servico_criado_em")

    op.drop_table("ordens_servico")
    op.drop_table("usuarios")
    op.drop_table("filiais")
