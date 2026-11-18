from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from osapp.db import Base
from osapp.models.tipos import DataHoraUTC

TIPO_LOGIN = "LOGIN"
TIPO_IP = "IP"


class TentativaLogin(Base):
    """Falhas de login por login digitado ou por IP, com o próximo instante permitido.

    ``chave`` é o HMAC-SHA256 (hex) do login normalizado ou do IP, com o segredo
    OS_HMAC_SEGREDO: nem o IP nem o login digitado são gravados.
    """

    __tablename__ = "tentativas_login"
    __table_args__ = (UniqueConstraint("tipo", "chave"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    chave: Mapped[str] = mapped_column(String(64))
    tipo: Mapped[str] = mapped_column(String(5))
    falhas: Mapped[int] = mapped_column(default=0, server_default="0")
    proximo_permitido_em: Mapped[datetime | None] = mapped_column(DataHoraUTC())
    atualizado_em: Mapped[datetime] = mapped_column(DataHoraUTC())
