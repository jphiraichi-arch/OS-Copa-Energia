"""Situação de uma Ordem de Serviço num instante, refeita pelo histórico. Módulo puro.

Prompt 25: o status num instante t vem dos eventos de os_eventos com data_hora < t (a
última transição antes de t vale), nunca do status atual nem das colunas de instante:
'Desfazer início' apaga inicio_execucao_em, então as colunas mudam depois do fato,
enquanto o histórico nunca muda.

Eventos usados: CRIACAO (a ordem passa a existir como ABERTA) e STATUS (valor_novo é o
código do novo status). Os demais tipos são ignorados.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NamedTuple
from zoneinfo import ZoneInfo

from osapp.services import status as _status

TIPO_CRIACAO = "CRIACAO"
TIPO_STATUS = "STATUS"


class Marco(NamedTuple):
    """O mínimo de um evento para refazer a linha do tempo."""

    data_hora: datetime
    tipo: str
    valor_novo: str | None = None


@dataclass(frozen=True)
class Situacao:
    """A ordem vista no instante t (tudo antes de t; nada do que veio depois)."""

    status: str | None  # None: ainda não existia em t
    inicio: datetime | None  # último início de execução não desfeito antes de t
    concluida_em: datetime | None  # conclusão antes de t
    cancelada_em: datetime | None  # cancelamento antes de t


def _em_ordem(eventos: Iterable) -> list:
    # sorted é estável: eventos no mesmo instante mantêm a ordem recebida (a do id).
    return sorted(eventos, key=lambda e: e.data_hora)


def situacao_em(eventos: Iterable, t: datetime) -> Situacao:
    """Status, início válido, conclusão e cancelamento como estavam em ``t``."""
    status = inicio = concluida = cancelada = None
    for e in _em_ordem(eventos):
        if e.data_hora >= t:
            break
        if e.tipo == TIPO_CRIACAO:
            status = _status.ABERTA
        elif e.tipo == TIPO_STATUS and e.valor_novo:
            status = e.valor_novo
            if status == _status.EM_EXECUCAO:
                inicio = e.data_hora
            elif status == _status.ABERTA:
                inicio = None  # início desfeito
            elif status == _status.CONCLUIDA:
                concluida = e.data_hora
            elif status == _status.CANCELADA:
                cancelada = e.data_hora
    if status not in (_status.EM_EXECUCAO, _status.CONCLUIDA):
        inicio = None
    return Situacao(status, inicio, concluida, cancelada)


def status_em(eventos: Iterable, t: datetime) -> str | None:
    """O status em ``t``: o da última transição antes de t (None se a ordem não existia)."""
    return situacao_em(eventos, t).status


def periodo_do_mes(ano: int, mes: int, tz: str) -> tuple[datetime, datetime]:
    """[00:00 do dia 1 de mes, 00:00 do dia 1 do mês seguinte) no fuso ``tz``, em UTC."""
    fuso = ZoneInfo(tz)
    inicio = datetime(ano, mes, 1, tzinfo=fuso)
    proximo = (
        datetime(ano + 1, 1, 1, tzinfo=fuso)
        if mes == 12
        else datetime(ano, mes + 1, 1, tzinfo=fuso)
    )
    return inicio.astimezone(UTC), proximo.astimezone(UTC)
