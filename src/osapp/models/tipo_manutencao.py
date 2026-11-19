from __future__ import annotations

from sqlalchemy import String, true
from sqlalchemy.orm import Mapped, mapped_column

from osapp.db import Base


class TipoManutencao(Base):
    """Tipo de manutenção. Tabela (não enum) para mudar a lista sem migração."""

    __tablename__ = "tipos_manutencao"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nome: Mapped[str] = mapped_column(String(60))
    ordem: Mapped[int]
    ativo: Mapped[bool] = mapped_column(default=True, server_default=true())
