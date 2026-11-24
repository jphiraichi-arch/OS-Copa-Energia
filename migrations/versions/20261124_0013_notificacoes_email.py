"""notificações por e-mail: endereço confirmado e fila de envio

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-24

Upgrade:
- usuario_notificacao (1:1 com usuarios, só para quem cadastrar um endereço): email,
  email_confirmado_em, notificacoes_ativas (falso), urgencia_minima ('baixa'), e o código
  de confirmação (só o HMAC), validade, tentativas, último envio e a janela do limite por
  hora. Nenhuma linha é criada: ninguém recebe nada até cadastrar e confirmar um e-mail.
- email_fila: a caixa de saída transacional (uma linha por mensagem).
Downgrade: apaga as duas tabelas. Os endereços, as confirmações e as mensagens da fila
(inclusive as pendentes) se perdem; nada mais no banco depende delas.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from osapp.models.tipos import DataHoraUTC

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "usuario_notificacao",
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("email_confirmado_em", DataHoraUTC(), nullable=True),
        sa.Column("notificacoes_ativas", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("urgencia_minima", sa.String(length=12), server_default="baixa", nullable=False),
        sa.Column("codigo_hash", sa.String(length=64), nullable=True),
        sa.Column("codigo_expira_em", DataHoraUTC(), nullable=True),
        sa.Column("codigo_tentativas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("codigo_enviado_em", DataHoraUTC(), nullable=True),
        sa.Column("codigo_janela_inicio", DataHoraUTC(), nullable=True),
        sa.Column("codigo_envios_janela", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "urgencia_minima IN ('baixa', 'alta', 'emergencial')",
            name=op.f("ck_usuario_notificacao_urgencia_minima_valida"),
        ),
        sa.CheckConstraint(
            "notificacoes_ativas = false"
            " OR (email IS NOT NULL AND email_confirmado_em IS NOT NULL)",
            name=op.f("ck_usuario_notificacao_ativas_exige_confirmado"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_usuario_notificacao_usuario_id_usuarios"),
        ),
        sa.PrimaryKeyConstraint("usuario_id", name=op.f("pk_usuario_notificacao")),
    )
    op.create_table(
        "email_fila",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("destinatario", sa.String(length=254), nullable=False),
        sa.Column("assunto", sa.String(length=200), nullable=False),
        sa.Column("corpo", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("tentativas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("proxima_tentativa_em", DataHoraUTC(), nullable=False),
        sa.Column("bloqueado_ate", DataHoraUTC(), nullable=True),
        sa.Column("ultimo_erro", sa.String(length=200), nullable=True),
        sa.Column("criado_em", DataHoraUTC(), nullable=False),
        sa.Column("enviado_em", DataHoraUTC(), nullable=True),
        sa.Column("os_id", sa.Integer(), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pendente', 'enviando', 'enviado', 'falhou', 'cancelado')",
            name=op.f("ck_email_fila_status_valido"),
        ),
        sa.CheckConstraint(
            "tipo IN ('nova_solicitacao', 'codigo_confirmacao')",
            name=op.f("ck_email_fila_tipo_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["os_id"], ["ordens_servico.id"], name=op.f("fk_email_fila_os_id_ordens_servico")
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuarios.id"], name=op.f("fk_email_fila_usuario_id_usuarios")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_fila")),
    )
    op.create_index(
        "ix_email_fila_status_proxima",
        "email_fila",
        ["status", "proxima_tentativa_em"],
        unique=False,
    )
    op.create_index(op.f("ix_email_fila_os_id"), "email_fila", ["os_id"], unique=False)
    op.create_index(op.f("ix_email_fila_usuario_id"), "email_fila", ["usuario_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_email_fila_usuario_id"), table_name="email_fila")
    op.drop_index(op.f("ix_email_fila_os_id"), table_name="email_fila")
    op.drop_index("ix_email_fila_status_proxima", table_name="email_fila")
    op.drop_table("email_fila")
    op.drop_table("usuario_notificacao")
