"""Alertas de erro grave (prompt 33): contadores no banco, para valerem entre processos.

- ``alertas_erro``: uma linha por impressão digital (tipo da exceção + arquivo + linha):
  quando foi o último alerta e quantas ocorrências houve desde então.
- ``alertas_dia``: quantos e-mails de alerta saíram em cada dia (America/Sao_Paulo), para
  o teto diário.
Nenhuma mensagem de erro, valor de variável ou dado de usuário é gravado aqui.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column

from osapp.db import Base
from osapp.models.tipos import DataHoraUTC

IMPRESSAO_MAX = 200


class AlertaErro(Base):
    __tablename__ = "alertas_erro"

    impressao: Mapped[str] = mapped_column(String(IMPRESSAO_MAX), primary_key=True)
    ultimo_alerta_em: Mapped[datetime | None] = mapped_column(DataHoraUTC())
    ultima_ocorrencia_em: Mapped[datetime] = mapped_column(DataHoraUTC())
    ocorrencias_pendentes: Mapped[int] = mapped_column(default=0, server_default="0")


class AlertaDia(Base):
    __tablename__ = "alertas_dia"

    dia: Mapped[date] = mapped_column(Date(), primary_key=True)
    emails: Mapped[int] = mapped_column(default=0, server_default="0")
