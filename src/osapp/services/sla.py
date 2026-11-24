"""SLA (prompt 38): alvos por filial e urgência, prazos gravados na OS e a etiqueta.

- Alvos em minutos de relógio (um dia = 24 h; sem dias úteis nesta versão). Uma filial
  nova recebe os padrões.
- Os prazos são gravados na OS ao abrir (``prazo_inicio_em`` = aberta_em + início;
  ``prazo_solucao_em`` = aberta_em + solução), com os alvos daquele momento. Mudar a
  urgência enquanto ABERTA recalcula os dois (com evento). Mudar os alvos depois nunca
  muda ordens existentes: o cumprimento passado continua reproduzível.
- Só ordens com urgência (solicitações) têm prazo e etiqueta.
- Etiqueta (manutenção e administrador; o usuario não recebe nesta versão): ABERTA ->
  prazo de início; EM_EXECUCAO -> prazo de solução. 'Atrasada' depois do prazo; 'Vence
  em X' com 25% ou menos do alvo restando; 'No prazo' no resto.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from osapp.db import sessao
from osapp.models import SlaAlvo
from osapp.repositories import FilialRepo
from osapp.services import status as _status
from osapp.services.auth import carregar_ator
from osapp.services.erros import ErroValidacao
from osapp.services.permissoes import exigir_admin

logger = logging.getLogger(__name__)

NIVEIS = ("baixa", "media", "alta", "emergencial")
DIA = 1440
# urgência -> (início, solução) em minutos.
PADROES: dict[str, tuple[int, int]] = {
    "emergencial": (60, 8 * 60),
    "alta": (4 * 60, 2 * DIA),
    "media": (DIA, 5 * DIA),
    "baixa": (3 * DIA, 15 * DIA),
}
PRAZO_MAX_MIN = 365 * DIA
FRACAO_VENCE = 0.25

ATRASADA = "atrasada"
VENCE = "vence"
NO_PRAZO = "no_prazo"


# --- Etiqueta (pura) --------------------------------------------------------------------------


@dataclass(frozen=True)
class Etiqueta:
    codigo: str  # ATRASADA | VENCE | NO_PRAZO
    texto: str  # 'Atrasada', 'Vence em 45 min', 'No prazo'


def texto_duracao(minutos: int) -> str:
    """'45 min', '3 h', '2 d' (para baixo em h e d; minutos arredondados para cima)."""
    if minutos < 60:
        return f"{max(minutos, 1)} min"
    if minutos < DIA:
        return f"{minutos // 60} h"
    return f"{minutos // DIA} d"


def etiqueta(
    status: str,
    aberta_em: datetime | None,
    prazo_inicio_em: datetime | None,
    prazo_solucao_em: datetime | None,
    agora: datetime,
) -> Etiqueta | None:
    if aberta_em is None:
        return None
    if status == _status.ABERTA:
        prazo = prazo_inicio_em
    elif status == _status.EM_EXECUCAO:
        prazo = prazo_solucao_em
    else:
        return None
    if prazo is None:
        return None
    if agora > prazo:
        return Etiqueta(ATRASADA, "Atrasada")
    restante = prazo - agora
    duracao = prazo - aberta_em
    if duracao.total_seconds() > 0 and restante <= duracao * FRACAO_VENCE:
        minutos = math.ceil(restante.total_seconds() / 60)
        return Etiqueta(VENCE, f"Vence em {texto_duracao(minutos)}")
    return Etiqueta(NO_PRAZO, "No prazo")


# --- Prazos (sessão aberta) ---------------------------------------------------------------


def alvo(s: Session, filial_id: int, urgencia: str) -> tuple[int, int]:
    linha = s.scalars(
        select(SlaAlvo).where(SlaAlvo.filial_id == filial_id, SlaAlvo.urgencia == urgencia)
    ).one_or_none()
    if linha is not None:
        return linha.prazo_inicio_min, linha.prazo_solucao_min
    return PADROES[urgencia]


def prazos(
    s: Session, filial_id: int, urgencia: str | None, aberta_em: datetime | None
) -> tuple[datetime | None, datetime | None]:
    if urgencia is None or aberta_em is None or urgencia not in PADROES:
        return None, None
    inicio, solucao = alvo(s, filial_id, urgencia)
    return aberta_em + timedelta(minutes=inicio), aberta_em + timedelta(minutes=solucao)


def criar_padroes(s: Session, filial_id: int) -> None:
    """Uma filial nova recebe os alvos padrão."""
    existentes = set(s.scalars(select(SlaAlvo.urgencia).where(SlaAlvo.filial_id == filial_id)))
    for urgencia, (inicio, solucao) in PADROES.items():
        if urgencia not in existentes:
            s.add(
                SlaAlvo(
                    filial_id=filial_id,
                    urgencia=urgencia,
                    prazo_inicio_min=inicio,
                    prazo_solucao_min=solucao,
                )
            )
    s.flush()


# --- Administração --------------------------------------------------------------------------


@dataclass(frozen=True)
class AlvoDTO:
    urgencia: str
    prazo_inicio_min: int
    prazo_solucao_min: int


@dataclass(frozen=True)
class AlvosDaFilial:
    filial_id: int
    filial_codigo: str
    filial_nome: str
    alvos: tuple[AlvoDTO, ...]  # emergencial, alta, media, baixa


def listar_alvos(ator_id: int) -> list[AlvosDaFilial]:
    """Só administrador. Uma tabela por filial; urgências da mais à menos urgente."""
    exigir_admin(carregar_ator(ator_id))
    with sessao() as s:
        saida = []
        for filial in FilialRepo(s).listar():
            criar_padroes(s, filial.id)  # filial antiga sem linhas: recebe os padrões
            alvos = {
                a.urgencia: a
                for a in s.scalars(select(SlaAlvo).where(SlaAlvo.filial_id == filial.id))
            }
            saida.append(
                AlvosDaFilial(
                    filial.id,
                    filial.codigo,
                    filial.nome,
                    tuple(
                        AlvoDTO(u, alvos[u].prazo_inicio_min, alvos[u].prazo_solucao_min)
                        for u in reversed(NIVEIS)
                    ),
                )
            )
        return saida


def _minutos(campo: str, valor: object) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or not 0 < valor <= PRAZO_MAX_MIN:
        raise ErroValidacao(campo, "Informe um prazo maior que zero (até 365 dias).")
    return valor


def definir_alvo(
    ator_id: int,
    filial_id: object,
    urgencia: object,
    prazo_inicio_min: object,
    prazo_solucao_min: object,
) -> AlvoDTO:
    """Só administrador. Vale para ordens abertas daqui em diante; não muda as existentes.
    Toda mudança vai para o log com o id do administrador."""
    ator = carregar_ator(ator_id)
    exigir_admin(ator)
    if urgencia not in PADROES:
        raise ErroValidacao("urgencia", "Urgência inválida.")
    inicio = _minutos("prazo_inicio_min", prazo_inicio_min)
    solucao = _minutos("prazo_solucao_min", prazo_solucao_min)
    if solucao < inicio:
        raise ErroValidacao("prazo_solucao_min", "A solução não pode ter prazo menor que o início.")
    with sessao() as s:
        if not isinstance(filial_id, int) or FilialRepo(s).obter(filial_id) is None:
            raise ErroValidacao("filial_id", "Filial não encontrada.")
        criar_padroes(s, filial_id)
        linha = s.scalars(
            select(SlaAlvo).where(SlaAlvo.filial_id == filial_id, SlaAlvo.urgencia == urgencia)
        ).one()
        antes = (linha.prazo_inicio_min, linha.prazo_solucao_min)
        linha.prazo_inicio_min, linha.prazo_solucao_min = inicio, solucao
        logger.info(
            "SLA alterado: filial_id=%s urgencia=%s inicio %s->%s solucao %s->%s admin_id=%s.",
            filial_id,
            urgencia,
            antes[0],
            inicio,
            antes[1],
            solucao,
            ator.usuario_id,
        )
        return AlvoDTO(urgencia, inicio, solucao)


# --- Relatório (puro) -----------------------------------------------------------------------


@dataclass(frozen=True)
class Cumprimento:
    dentro: int
    total: int  # denominador (0 -> '—')

    @property
    def percentual(self) -> float | None:
        return None if self.total == 0 else self.dentro * 100 / self.total


def cumprimento(itens, fim: datetime) -> tuple[Cumprimento, Cumprimento]:
    """``itens``: (prazo_inicio_em, prazo_solucao_em, inicio, concluida) com a situação no
    fim do período. Entra no denominador quem já venceu até ``fim`` ou já cumpriu (iniciou
    / concluiu até ``fim``); dentro = cumpriu até o prazo (inclusive)."""
    ini_d = ini_t = sol_d = sol_t = 0
    for prazo_ini, prazo_sol, inicio, concluida in itens:
        if prazo_ini is not None and (inicio is not None or prazo_ini < fim):
            ini_t += 1
            ini_d += inicio is not None and inicio <= prazo_ini
        if prazo_sol is not None and (concluida is not None or prazo_sol < fim):
            sol_t += 1
            sol_d += concluida is not None and concluida <= prazo_sol
    return Cumprimento(int(ini_d), ini_t), Cumprimento(int(sol_d), sol_t)


def texto_cumprimento(c: Cumprimento) -> str:
    """'92% (46 de 50)' ou '—'."""
    if c.percentual is None:
        return "—"
    pct = c.percentual
    numero = f"{pct:.0f}" if abs(pct - round(pct)) < 0.05 else f"{pct:.1f}".replace(".", ",")
    return f"{numero}% ({c.dentro} de {c.total})"
