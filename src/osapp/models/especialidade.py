"""Especialidade da manutenção (prompt 37): Mecânica, Elétrica, Predial/civil, Utilidades.

Tabela (não enum), como tipos_manutencao: o administrador mantém a lista. Desativada não
é escolhida em OS nova, mas continua nas antigas. ``usuario_especialidades`` prepara o
filtro de notificações (ainda não filtra nada).
"""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, String, Table, true
from sqlalchemy.orm import Mapped, mapped_column

from osapp.db import Base

usuario_especialidades = Table(
    "usuario_especialidades",
    Base.metadata,
    Column("usuario_id", ForeignKey("usuarios.id"), primary_key=True),
    Column("especialidade_id", ForeignKey("especialidades.id"), primary_key=True),
)


class Especialidade(Base):
    __tablename__ = "especialidades"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nome: Mapped[str] = mapped_column(String(60))
    ordem: Mapped[int]
    ativo: Mapped[bool] = mapped_column(default=True, server_default=true())
