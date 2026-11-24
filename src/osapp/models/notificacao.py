"""Notificações por e-mail (prompt 32): endereço confirmado do usuário e a fila de envio.

``usuario_notificacao`` é 1:1 com ``usuarios`` (só existe para quem cadastrou um
endereço): o dado pessoal fica fora da tabela de usuários e alterar o e-mail não mexe na
versão (trava otimista) do cadastro.

``email_fila`` é a caixa de saída transacional: a linha é gravada na mesma transação da
OS; um trabalhador por processo envia depois (services/fila_email.py).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from osapp.db import Base
from osapp.models.tipos import DataHoraUTC

EMAIL_MAX = 254

FILA_PENDENTE = "pendente"
FILA_ENVIANDO = "enviando"
FILA_ENVIADO = "enviado"
FILA_FALHOU = "falhou"
FILA_CANCELADO = "cancelado"
FILA_STATUS = (FILA_PENDENTE, FILA_ENVIANDO, FILA_ENVIADO, FILA_FALHOU, FILA_CANCELADO)

TIPO_NOVA_SOLICITACAO = "nova_solicitacao"
TIPO_CODIGO = "codigo_confirmacao"
TIPOS_EMAIL = (TIPO_NOVA_SOLICITACAO, TIPO_CODIGO)

URGENCIAS_MINIMAS = ("baixa", "alta", "emergencial")


def _lista(valores: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in valores)


class UsuarioNotificacao(Base):
    __tablename__ = "usuario_notificacao"
    __table_args__ = (
        CheckConstraint(
            f"urgencia_minima IN ({_lista(URGENCIAS_MINIMAS)})", name="urgencia_minima_valida"
        ),
        # Notificação ligada exige endereço confirmado (o serviço garante; o banco confere).
        CheckConstraint(
            "notificacoes_ativas = false"
            " OR (email IS NOT NULL AND email_confirmado_em IS NOT NULL)",
            name="ativas_exige_confirmado",
        ),
    )

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(EMAIL_MAX))
    email_confirmado_em: Mapped[datetime | None] = mapped_column(DataHoraUTC())
    notificacoes_ativas: Mapped[bool] = mapped_column(default=False, server_default=false())
    urgencia_minima: Mapped[str] = mapped_column(
        String(12), default="baixa", server_default="baixa"
    )
    # Código de confirmação: só o HMAC (OS_HMAC_SEGREDO), nunca o código.
    codigo_hash: Mapped[str | None] = mapped_column(String(64))
    codigo_expira_em: Mapped[datetime | None] = mapped_column(DataHoraUTC())
    codigo_tentativas: Mapped[int] = mapped_column(default=0, server_default="0")
    codigo_enviado_em: Mapped[datetime | None] = mapped_column(DataHoraUTC())
    # Limite de 5 códigos por hora: início da janela e quantos foram pedidos nela.
    codigo_janela_inicio: Mapped[datetime | None] = mapped_column(DataHoraUTC())
    codigo_envios_janela: Mapped[int] = mapped_column(default=0, server_default="0")


class EmailFila(Base):
    __tablename__ = "email_fila"
    __table_args__ = (
        CheckConstraint(f"status IN ({_lista(FILA_STATUS)})", name="status_valido"),
        CheckConstraint(f"tipo IN ({_lista(TIPOS_EMAIL)})", name="tipo_valido"),
        Index("ix_email_fila_status_proxima", "status", "proxima_tentativa_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))
    destinatario: Mapped[str] = mapped_column(String(EMAIL_MAX))
    assunto: Mapped[str] = mapped_column(String(200))
    corpo: Mapped[str] = mapped_column(Text())
    status: Mapped[str] = mapped_column(String(10), default=FILA_PENDENTE)
    tentativas: Mapped[int] = mapped_column(default=0, server_default="0")
    proxima_tentativa_em: Mapped[datetime] = mapped_column(DataHoraUTC())
    bloqueado_ate: Mapped[datetime | None] = mapped_column(DataHoraUTC())
    ultimo_erro: Mapped[str | None] = mapped_column(String(200))
    criado_em: Mapped[datetime] = mapped_column(DataHoraUTC())
    enviado_em: Mapped[datetime | None] = mapped_column(DataHoraUTC())
    os_id: Mapped[int | None] = mapped_column(ForeignKey("ordens_servico.id"), index=True)
    # Dono do endereço: para cancelar o que está pendente quando ele remove o e-mail.
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
