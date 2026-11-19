"""Rótulos de status, urgência/prioridade, origem e papel. Módulo puro (sem Flet).

Os selos mostram sempre a palavra; a cor (ui/theme.py) é só reforço.
"""

from __future__ import annotations

from datetime import UTC, datetime

from osapp.services import status as _status
from osapp.services.auth import PAPEIS
from osapp.services.ordens import NIVEIS, ORIGENS

NIVEL: dict[str, str] = {
    "baixa": "Baixa",
    "media": "Média",
    "alta": "Alta",
    "emergencial": "Emergencial",
}
STATUS: dict[str, str] = dict(_status.ROTULOS)
ORIGEM: dict[str, str] = {"solicitacao": "Solicitação", "manutencao": "Manutenção"}
PAPEL: dict[str, str] = {
    "usuario": "Usuário",
    "manutencao": "Manutenção",
    "admin": "Administrador",
}
SEM_NIVEL = "Não definida"

_SEM_DATA = datetime.max.replace(tzinfo=UTC)
# Ordem de atendimento: Emergencial primeiro.
_ORDEM_NIVEL = {nivel: n for n, nivel in enumerate(reversed(NIVEIS))}


def nivel(valor: str | None) -> str:
    """Rótulo de urgência ou prioridade ('Não definida' quando vazio)."""
    return NIVEL.get(valor, valor) if valor else SEM_NIVEL


def status(valor: str) -> str:
    return STATUS.get(valor, valor)


def origem(valor: str) -> str:
    return ORIGEM.get(valor, valor)


def papel(valor: str) -> str:
    return PAPEL.get(valor, valor)


def ordenar_solicitacoes_abertas(itens) -> list:
    """'Solicitações abertas': urgência (Emergencial primeiro), depois a mais antiga.

    Cada item precisa de ``urgencia`` e ``aberta_em``; sem urgência vai para o fim.
    """

    def chave(item):
        aberta = item.aberta_em or _SEM_DATA  # instantes do serviço: sempre em UTC
        return (_ORDEM_NIVEL.get(item.urgencia, len(_ORDEM_NIVEL)), aberta, item.id)

    return sorted(itens, key=chave)


# Conferência ao importar: nenhum valor sem rótulo.
assert set(NIVEL) == set(NIVEIS) and set(ORIGEM) == set(ORIGENS) and set(PAPEL) == set(PAPEIS)
