from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from osapp.db import Base
from osapp.models.tipos import DataHoraUTC
from osapp.models.usuario import Usuario


class UsuarioEvento(Base):
    """Histórico de mudanças em usuários. Só recebe inserções (nunca UPDATE ou DELETE).

    ``admin_id`` é quem fez a mudança (None: linha de comando no servidor). Mudança de
    senha grava só 'senha redefinida' ou 'senha alterada', nunca a senha nem o hash.
    """

    __tablename__ = "usuarios_eventos"
    __table_args__ = (Index("ix_usuarios_eventos_usuario_id", "usuario_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    data_hora: Mapped[datetime] = mapped_column(DataHoraUTC())
    campo: Mapped[str] = mapped_column(String(40))
    valor_antigo: Mapped[str | None] = mapped_column(String(200))
    valor_novo: Mapped[str | None] = mapped_column(String(200))

    admin: Mapped[Usuario | None] = relationship(foreign_keys=[admin_id])
