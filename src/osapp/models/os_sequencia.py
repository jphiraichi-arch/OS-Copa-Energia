from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from osapp.db import Base


class OsSequencia(Base):
    """Último número de OS usado, por filial e por ano (no fuso OS_TZ)."""

    __tablename__ = "os_sequencias"

    filial_id: Mapped[int] = mapped_column(ForeignKey("filiais.id"), primary_key=True)
    ano: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    ultimo_numero: Mapped[int]
