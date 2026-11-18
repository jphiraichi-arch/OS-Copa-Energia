from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from osapp.models import CategoriaCusto, Equipamento


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


class EquipamentoRepo:
    def __init__(self, sessao: Session) -> None:
        self._s = sessao

    def obter(self, equipamento_id: int) -> Equipamento | None:
        return self._s.get(Equipamento, equipamento_id)

    def obter_por_nome(self, filial_id: int, nome: str) -> Equipamento | None:
        return self._s.scalars(
            select(Equipamento).where(Equipamento.filial_id == filial_id, Equipamento.nome == nome)
        ).first()

    def listar(self, filial_id: int, so_ativos: bool = True) -> list[Equipamento]:
        consulta = (
            select(Equipamento)
            .where(Equipamento.filial_id == filial_id)
            .order_by(Equipamento.nome, Equipamento.id)
        )
        if so_ativos:
            consulta = consulta.where(Equipamento.ativo.is_(True))
        return list(self._s.scalars(consulta))

    def adicionar(self, equipamento: Equipamento) -> Equipamento:
        self._s.add(equipamento)
        self._s.flush()
        return equipamento
