from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from osapp.db import Base
from osapp.models.tipos import DataHoraUTC
from osapp.models.usuario import Usuario


def _agora_utc() -> datetime:
    return datetime.now(UTC)


class OsEvento(Base):
    """Registro de auditoria de uma OS. Somente inserção: nunca é alterado nem apagado."""

    __tablename__ = "os_eventos"
    __table_args__ = (Index("ix_os_eventos_os_id", "os_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    os_id: Mapped[int] = mapped_column(ForeignKey("ordens_servico.id"))
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    data_hora: Mapped[datetime] = mapped_column(DataHoraUTC(), default=_agora_utc)
    tipo: Mapped[str] = mapped_column(String(20))
    campo: Mapped[str | None] = mapped_column(String(50))
    valor_antigo: Mapped[str | None] = mapped_column(Text)
    valor_novo: Mapped[str | None] = mapped_column(Text)

    usuario: Mapped[Usuario] = relationship()
