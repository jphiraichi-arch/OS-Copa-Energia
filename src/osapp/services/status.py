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


# --- Transições -----------------------------------------------------------------------
# Quem pode fazer a transição, além do administrador (que pode todas as da tabela):
QUALQUER_USUARIO_DA_FILIAL = "QUALQUER_USUARIO_DA_FILIAL"
SOMENTE_EXECUTOR = "SOMENTE_EXECUTOR"

# Tabela única de movimentos permitidos: (origem, destino) -> quem pode.
# O que não está aqui é proibido. Um novo status é uma nova entrada.
TRANSICOES: dict[tuple[str, str], str] = {
    (ABERTA, EM_EXECUCAO): QUALQUER_USUARIO_DA_FILIAL,  # iniciar
    (EM_EXECUCAO, ABERTA): SOMENTE_EXECUTOR,  # desfazer início
    (EM_EXECUCAO, CONCLUIDA): SOMENTE_EXECUTOR,  # concluir
}

# Status em que a OS está encerrada: só administrador edita, e os campos de
# "realizado" existem.
ENCERRADOS: frozenset[str] = frozenset({CONCLUIDA})


def quem_pode_transicionar(origem: str, destino: str) -> str | None:
    """Regra da transição, ou None se ela não estiver na tabela."""
    return TRANSICOES.get((origem, destino))


def encerrado(status: str) -> bool:
    return status in ENCERRADOS
