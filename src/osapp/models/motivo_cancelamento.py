"""Motivos de cancelamento (prompt 41). Tabela editável pelo administrador; 'Outro' exige
texto. As ordens canceladas antes do prompt 41 ficam sem motivo."""

from __future__ import annotations

from sqlalchemy import String, true
from sqlalchemy.orm import Mapped, mapped_column

from osapp.db import Base

CODIGO_OUTRO = "OUTRO"
CODIGO_FORA_DO_ESCOPO = "FORA_ESCOPO_TI"


class MotivoCancelamento(Base):
    __tablename__ = "motivos_cancelamento"

    id: Mapped[int] = mapped_column(primary_key=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True)
    nome: Mapped[str] = mapped_column(String(60))
    ordem: Mapped[int]
    ativo: Mapped[bool] = mapped_column(default=True, server_default=true())
