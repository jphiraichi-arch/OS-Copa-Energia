"""'Lembrar de mim por 7 dias' (prompt 35).

Uma linha por token emitido. ``familia`` junta todas as rotações de um mesmo login num
aparelho. O token nunca é gravado: só o SHA-256 (``token_hash``). ``ultimo_uso_em``
preenchido quer dizer que o token já foi trocado por outro (rotação): apresentá-lo de
novo é sinal de cópia. ``rotulo_aparelho`` é um texto curto ('Chrome em Android'), nunca
o user agent cru nem o IP.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from osapp.db import Base
from osapp.models.tipos import DataHoraUTC


class SessaoLembrada(Base):
    __tablename__ = "sessoes_lembradas"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    familia: Mapped[str] = mapped_column(String(32), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    criado_em: Mapped[datetime] = mapped_column(DataHoraUTC())
    expira_em: Mapped[datetime] = mapped_column(DataHoraUTC())
    ultimo_uso_em: Mapped[datetime | None] = mapped_column(DataHoraUTC())
    rotulo_aparelho: Mapped[str] = mapped_column(String(60))
    revogado_em: Mapped[datetime | None] = mapped_column(DataHoraUTC())
