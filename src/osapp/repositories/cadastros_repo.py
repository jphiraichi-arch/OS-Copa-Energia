from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from osapp.models import CategoriaCusto, TipoManutencao


class CategoriaCustoRepo:
    def __init__(self, sessao: Session) -> None:
        self._s = sessao

    def obter(self, categoria_id: int) -> CategoriaCusto | None:
        return self._s.get(CategoriaCusto, categoria_id)

    def obter_por_codigo(self, codigo: str) -> CategoriaCusto | None:
        return self._s.scalars(
            select(CategoriaCusto).where(CategoriaCusto.codigo == codigo)
        ).one_or_none()

    def listar(self, so_ativas: bool = True) -> list[CategoriaCusto]:
        consulta = select(CategoriaCusto).order_by(CategoriaCusto.ordem, CategoriaCusto.id)
        if so_ativas:
            consulta = consulta.where(CategoriaCusto.ativo.is_(True))
        return list(self._s.scalars(consulta))

    def adicionar(self, categoria: CategoriaCusto) -> CategoriaCusto:
        self._s.add(categoria)
        self._s.flush()
        return categoria


class TipoManutencaoRepo:
    def __init__(self, sessao: Session) -> None:
        self._s = sessao

    def obter(self, tipo_id: int) -> TipoManutencao | None:
        return self._s.get(TipoManutencao, tipo_id)

    def listar(self, so_ativos: bool = True) -> list[TipoManutencao]:
        consulta = select(TipoManutencao).order_by(TipoManutencao.ordem, TipoManutencao.id)
        if so_ativos:
            consulta = consulta.where(TipoManutencao.ativo.is_(True))
        return list(self._s.scalars(consulta))
