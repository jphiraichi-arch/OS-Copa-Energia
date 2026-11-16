"""Status da OS, definidos uma única vez. Um novo status é uma nova entrada aqui."""

from __future__ import annotations

ABERTA = "ABERTA"
EM_EXECUCAO = "EM_EXECUCAO"
CONCLUIDA = "CONCLUIDA"

STATUS_INICIAL = ABERTA

# Na ordem em que aparecem na interface.
ROTULOS: dict[str, str] = {
    ABERTA: "Aberta",
    EM_EXECUCAO: "Em execução",
    CONCLUIDA: "Concluída",
}


def status_conhecido(status: object) -> bool:
    return isinstance(status, str) and status in ROTULOS


def rotulo(status: str) -> str:
    """Rótulo em português; um status desconhecido é devolvido como está."""
    return ROTULOS.get(status, status)
