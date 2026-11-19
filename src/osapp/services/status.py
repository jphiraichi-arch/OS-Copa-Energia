"""Status da Ordem de Serviço e as transições, definidos uma única vez (dados).

Quem pode cada transição é decidido em services/ordens.py, pelas mesmas funções que
calculam os flags de ``acoes``; aqui ficam só os status, os movimentos e quem os faz.
"""

from __future__ import annotations

ABERTA = "ABERTA"
EM_EXECUCAO = "EM_EXECUCAO"
CONCLUIDA = "CONCLUIDA"
CANCELADA = "CANCELADA"

STATUS_INICIAL = ABERTA

# Na ordem em que aparecem na interface.
ROTULOS: dict[str, str] = {
    ABERTA: "Aberta",
    EM_EXECUCAO: "Em execução",
    CONCLUIDA: "Concluída",
    CANCELADA: "Cancelada",
}


def status_conhecido(status: object) -> bool:
    return isinstance(status, str) and status in ROTULOS


def rotulo(status: str) -> str:
    """Rótulo em português; um status desconhecido é devolvido como está."""
    return ROTULOS.get(status, status)


# --- Transições -----------------------------------------------------------------------
# Quem pode, além do administrador (que pode todas as da tabela):
MANUTENCAO_DA_FILIAL = "MANUTENCAO_DA_FILIAL"
SOMENTE_EXECUTOR = "SOMENTE_EXECUTOR"
SOMENTE_SOLICITANTE = "SOMENTE_SOLICITANTE"  # quem abriu a solicitação

INICIAR = "iniciar"
DESFAZER_INICIO = "desfazer_inicio"
CONCLUIR = "concluir"
CANCELAR = "cancelar"

# Tabela única de movimentos permitidos: ação -> (origem, destino, quem pode).
# O que não está aqui é proibido. Um novo status é uma nova entrada.
TRANSICOES: dict[str, tuple[str, str, str]] = {
    INICIAR: (ABERTA, EM_EXECUCAO, MANUTENCAO_DA_FILIAL),
    DESFAZER_INICIO: (EM_EXECUCAO, ABERTA, SOMENTE_EXECUTOR),
    CONCLUIR: (EM_EXECUCAO, CONCLUIDA, SOMENTE_EXECUTOR),
    CANCELAR: (ABERTA, CANCELADA, SOMENTE_SOLICITANTE),
}

# Status finais: CONCLUIDA (só administrador edita) e CANCELADA (ninguém edita).
FINAIS: frozenset[str] = frozenset({CONCLUIDA, CANCELADA})
# Status em que a OS está concluída: os campos de "realizado" existem.
ENCERRADOS: frozenset[str] = frozenset({CONCLUIDA})


def transicao(acao: str) -> tuple[str, str, str]:
    return TRANSICOES[acao]


def encerrado(status: str) -> bool:
    return status in ENCERRADOS


def final(status: str) -> bool:
    return status in FINAIS
