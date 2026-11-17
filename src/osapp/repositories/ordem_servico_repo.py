from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from osapp.models import OrdemServico

LARGURA_SEQUENCIA = 6


class OrdemServicoRepo:
    def __init__(self, sessao: Session) -> None:
        self._s = sessao

    def obter(self, os_id: int) -> OrdemServico | None:
        return self._s.get(OrdemServico, os_id)

    def adicionar(self, ordem: OrdemServico) -> OrdemServico:
        self._s.add(ordem)
        self._s.flush()
        return ordem

    def listar(
        self,
        filial_id: int | None = None,
        status: str | None = None,
        busca: str | None = None,
        limite: int = 50,
        deslocamento: int = 0,
    ) -> list[OrdemServico]:
        """Lista da mais nova para a mais antiga, com filtros opcionais.

        A busca compara numero, titulo e descricao sem diferenciar maiúsculas; os
        caracteres % e _ do texto são escapados e valem como caracteres comuns.
        """
        consulta = select(OrdemServico)
        if filial_id is not None:
            consulta = consulta.where(OrdemServico.filial_id == filial_id)
        if status is not None:
            consulta = consulta.where(OrdemServico.status == status)
        if busca:
            consulta = consulta.where(
                or_(
                    OrdemServico.numero.icontains(busca, autoescape=True),
                    OrdemServico.titulo.icontains(busca, autoescape=True),
                    OrdemServico.descricao.icontains(busca, autoescape=True),
                )
            )
        consulta = (
            consulta.order_by(OrdemServico.criado_em.desc(), OrdemServico.id.desc())
            .limit(limite)
            .offset(deslocamento)
        )
        return list(self._s.scalars(consulta))

    def proximo_numero(self, ano: int) -> str:
        """Próximo número do ano, no estilo 'OS-2026-000001' (uma sequência por ano).

        Não reserva o número: a unicidade de ``numero`` é a rede de segurança e o
        serviço tenta de novo em caso de conflito.
        """
        prefixo = f"OS-{ano:04d}-"
        ultimo = self._s.scalars(
            select(OrdemServico.numero)
            .where(OrdemServico.numero.startswith(prefixo, autoescape=True))
            .order_by(func.length(OrdemServico.numero).desc(), OrdemServico.numero.desc())
            .limit(1)
        ).first()
        sequencia = int(ultimo[len(prefixo) :]) + 1 if ultimo else 1
        return f"{prefixo}{sequencia:0{LARGURA_SEQUENCIA}d}"

    def contar_por_status(self, filial_id: int | None = None) -> dict[str, int]:
        """Quantidade de OS em cada status agora (filial_id None = todas as filiais)."""
        consulta = select(OrdemServico.status, func.count()).group_by(OrdemServico.status)
        if filial_id is not None:
            consulta = consulta.where(OrdemServico.filial_id == filial_id)
        return {status: total for status, total in self._s.execute(consulta).all()}

    def contar_criadas(self, filial_id: int | None, inicio: datetime, fim: datetime) -> int:
        """OS criadas em [inicio, fim)."""
        consulta = (
            select(func.count())
            .select_from(OrdemServico)
            .where(OrdemServico.criado_em >= inicio, OrdemServico.criado_em < fim)
        )
        if filial_id is not None:
            consulta = consulta.where(OrdemServico.filial_id == filial_id)
        return int(self._s.scalar(consulta) or 0)

    def listar_concluidas(
        self, filial_id: int | None, status: str, inicio: datetime, fim: datetime
    ) -> list[OrdemServico]:
        """OS no ``status`` dado com conclusão em [inicio, fim), da mais antiga à mais nova."""
        consulta = select(OrdemServico).where(
            OrdemServico.status == status,
            OrdemServico.concluido_em >= inicio,
            OrdemServico.concluido_em < fim,
        )
        if filial_id is not None:
            consulta = consulta.where(OrdemServico.filial_id == filial_id)
        consulta = consulta.order_by(OrdemServico.concluido_em, OrdemServico.id)
        return list(self._s.scalars(consulta))
