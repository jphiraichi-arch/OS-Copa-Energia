from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, raiseload

from osapp.models import Filial, OrdemServico, Usuario

LARGURA_SEQUENCIA = 6


class OrdemServicoRepo:
    def __init__(self, sessao: Session) -> None:
        self._s = sessao

    def obter(self, os_id: int) -> OrdemServico | None:
        return self._s.get(OrdemServico, os_id)

    def obter_sem_relacoes(self, os_id: int) -> OrdemServico | None:
        """Só a linha da OS. Acessar um relacionamento (itens, executor...) levanta
        erro em vez de carregá-lo."""
        return self._s.scalars(
            select(OrdemServico).where(OrdemServico.id == os_id).options(raiseload("*"))
        ).one_or_none()

    def obter_por_numero(self, numero: str) -> OrdemServico | None:
        return self._s.scalars(
            select(OrdemServico).where(OrdemServico.numero == numero)
        ).one_or_none()

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
        origem: str | None = None,
    ) -> list[OrdemServico]:
        """Lista da mais nova para a mais antiga, com filtros opcionais.

        A busca compara numero, titulo e descricao sem diferenciar maiúsculas; os
        caracteres % e _ do texto são escapados e valem como caracteres comuns.
        """
        consulta = _filtrar(select(OrdemServico), filial_id, status, busca, origem)
        consulta = (
            consulta.order_by(OrdemServico.criado_em.desc(), OrdemServico.id.desc())
            .limit(limite)
            .offset(deslocamento)
        )
        return list(self._s.scalars(consulta))

    # --- Relatório de tempos: só as colunas necessárias, filtros na consulta ----------

    def tempos_de_solicitacoes(
        self, filial_id: int | None, inicio: datetime, fim: datetime, status: tuple[str, ...]
    ) -> list[tuple]:
        """(id, urgencia, aberta_em, inicio_execucao_em, concluida_em) das solicitações
        (nunca canceladas) abertas em [inicio, fim) com um dos ``status``."""
        consulta = select(
            OrdemServico.id,
            OrdemServico.urgencia,
            OrdemServico.aberta_em,
            OrdemServico.inicio_execucao_em,
            OrdemServico.concluida_em,
        ).where(
            OrdemServico.origem == "solicitacao",
            OrdemServico.status != "CANCELADA",
            OrdemServico.status.in_(status),
            OrdemServico.aberta_em >= inicio,
            OrdemServico.aberta_em < fim,
        )
        if filial_id is not None:
            consulta = consulta.where(OrdemServico.filial_id == filial_id)
        return [tuple(linha) for linha in self._s.execute(consulta.order_by(OrdemServico.id))]

    def abertas_de_solicitacoes(self, filial_id: int | None) -> list[datetime]:
        """aberta_em de cada solicitação ainda ABERTA (situação de agora)."""
        consulta = select(OrdemServico.aberta_em).where(
            OrdemServico.origem == "solicitacao", OrdemServico.status == "ABERTA"
        )
        if filial_id is not None:
            consulta = consulta.where(OrdemServico.filial_id == filial_id)
        return list(self._s.scalars(consulta))

    # --- Visão do solicitante: só as colunas permitidas, nunca a entidade inteira -----

    def _consulta_solicitante(self):
        return (
            select(*COLUNAS_SOLICITANTE)
            .join(Usuario, OrdemServico.criado_por_id == Usuario.id)
            .join(Filial, OrdemServico.filial_id == Filial.id)
        )

    def visao_solicitante(self, os_id: int):
        """Linha (mapeamento) com as colunas permitidas ao papel usuario, ou None."""
        consulta = self._consulta_solicitante().where(OrdemServico.id == os_id)
        return self._s.execute(consulta).mappings().one_or_none()

    def listar_visao_solicitante(
        self,
        filial_id: int,
        status: str | None = None,
        busca: str | None = None,
        limite: int = 50,
        deslocamento: int = 0,
    ) -> list:
        consulta = _filtrar(self._consulta_solicitante(), filial_id, status, busca, None)
        consulta = (
            consulta.order_by(OrdemServico.aberta_em.desc(), OrdemServico.id.desc())
            .limit(limite)
            .offset(deslocamento)
        )
        return list(self._s.execute(consulta).mappings())

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
            OrdemServico.concluida_em >= inicio,
            OrdemServico.concluida_em < fim,
        )
        if filial_id is not None:
            consulta = consulta.where(OrdemServico.filial_id == filial_id)
        consulta = consulta.order_by(OrdemServico.concluida_em, OrdemServico.id)
        return list(self._s.scalars(consulta))


# Colunas que o papel usuario pode receber (rótulos = nomes dos campos do DTO). origem e
# criado_por_id servem só para calcular as ações; o serviço não as repassa.
COLUNAS_SOLICITANTE = (
    OrdemServico.id.label("id"),
    OrdemServico.numero.label("numero"),
    OrdemServico.titulo.label("titulo"),
    OrdemServico.descricao.label("descricao"),
    OrdemServico.urgencia.label("urgencia"),
    OrdemServico.status.label("status"),
    OrdemServico.versao.label("versao"),
    Usuario.nome.label("solicitante"),
    Filial.codigo.label("filial_codigo"),
    OrdemServico.aberta_em.label("aberta_em"),
    OrdemServico.inicio_execucao_em.label("inicio_execucao_em"),
    OrdemServico.concluida_em.label("concluida_em"),
    OrdemServico.cancelada_em.label("cancelada_em"),
    OrdemServico.nota_conclusao.label("nota_conclusao"),
    OrdemServico.origem.label("origem"),
    OrdemServico.criado_por_id.label("criado_por_id"),
    OrdemServico.filial_id.label("filial_id"),
)


def _filtrar(consulta, filial_id, status, busca, origem):
    """Filtros comuns. A busca compara número, título e descrição, sem diferenciar
    maiúsculas; % e _ do texto valem como caracteres comuns."""
    if filial_id is not None:
        consulta = consulta.where(OrdemServico.filial_id == filial_id)
    if status is not None:
        consulta = consulta.where(OrdemServico.status == status)
    if origem is not None:
        consulta = consulta.where(OrdemServico.origem == origem)
    if busca:
        consulta = consulta.where(
            or_(
                OrdemServico.numero.icontains(busca, autoescape=True),
                OrdemServico.titulo.icontains(busca, autoescape=True),
                OrdemServico.descricao.icontains(busca, autoescape=True),
            )
        )
    return consulta
