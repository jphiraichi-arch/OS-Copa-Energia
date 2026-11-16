from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from osapp.models import OsEvento


class OsEventoRepo:
    """Registro somente de inserção: não há, de propósito, alteração nem exclusão."""

    def __init__(self, sessao: Session) -> None:
        self._s = sessao

    def adicionar(self, evento: OsEvento) -> OsEvento:
        self._s.add(evento)
        self._s.flush()
        return evento

    def listar_por_os(self, os_id: int) -> list[OsEvento]:
        """Eventos da OS, do mais antigo para o mais novo."""
        return list(
            self._s.scalars(
                select(OsEvento)
                .where(OsEvento.os_id == os_id)
                .order_by(OsEvento.data_hora, OsEvento.id)
            )
        )
