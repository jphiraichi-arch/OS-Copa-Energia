from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String, false, true
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from osapp.db import Base
from osapp.models.filial import Filial
from osapp.models.tipos import DataHoraUTC


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(100))
    login: Mapped[str] = mapped_column(String(50), unique=True)
    senha_hash: Mapped[str] = mapped_column(String(255))
    filial_id: Mapped[int] = mapped_column(ForeignKey("filiais.id"))
    is_admin: Mapped[bool] = mapped_column(default=False, server_default=false())
    # Gerente: vê o relatório completo da própria filial. Administrador prevalece.
    is_gerente: Mapped[bool] = mapped_column(default=False, server_default=false())
    ativo: Mapped[bool] = mapped_column(default=True, server_default=true())
    tentativas_falhas: Mapped[int] = mapped_column(default=0, server_default="0")
    bloqueado_ate: Mapped[datetime | None] = mapped_column(DataHoraUTC())

    filial: Mapped[Filial] = relationship()

    @validates("login")
    def _login_em_minusculas(self, _chave: str, valor: str) -> str:
        return valor.lower()
