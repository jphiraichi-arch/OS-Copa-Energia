"""Visualizações de uma OS pela manutenção (prompt 42).

Uma linha por (OS, usuário): a primeira e a última vez que a pessoa abriu o detalhe.
``primeira_visualizacao_em`` nunca muda depois de gravada: a métrica de tempo até a
visualização é reproduzível para meses passados.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from osapp.db import Base
from osapp.models.tipos import DataHoraUTC


class OsVisualizacao(Base):
    __tablename__ = "os_visualizacoes"
    __table_args__ = (UniqueConstraint("os_id", "usuario_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    os_id: Mapped[int] = mapped_column(ForeignKey("ordens_servico.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    primeira_visualizacao_em: Mapped[datetime] = mapped_column(DataHoraUTC())
    ultima_visualizacao_em: Mapped[datetime] = mapped_column(DataHoraUTC())
