from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from osapp.models import Filial


class FilialRepo:
    def __init__(self, sessao: Session) -> None:
        self._s = sessao

    def obter(self, filial_id: int) -> Filial | None:
        return self._s.get(Filial, filial_id)

    def obter_por_codigo(self, codigo: str) -> Filial | None:
        return self._s.scalars(select(Filial).where(Filial.codigo == codigo)).one_or_none()

    def listar(self) -> list[Filial]:
        return list(self._s.scalars(select(Filial).order_by(Filial.codigo)))

    def adicionar(self, filial: Filial) -> Filial:
        self._s.add(filial)
        self._s.flush()
        return filial
