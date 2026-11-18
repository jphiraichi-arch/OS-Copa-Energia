from __future__ import annotations

from sqlalchemy import ForeignKey, String, true
from sqlalchemy.orm import Mapped, mapped_column

from osapp.db import Base


class Equipamento(Base):
    __tablename__ = "equipamentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    filial_id: Mapped[int] = mapped_column(ForeignKey("filiais.id"))
    nome: Mapped[str] = mapped_column(String(120))
    codigo_sap: Mapped[str | None] = mapped_column(String(40))  # integração SAP futura
    ativo: Mapped[bool] = mapped_column(default=True, server_default=true())
