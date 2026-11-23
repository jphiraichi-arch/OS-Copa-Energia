"""Seções do formulário da Ordem de Serviço por papel e status. Módulo puro (sem Flet).

Um só layout em todas as etapas (decisão de 21/11/2026):
- SOLICITAÇÃO (título, descrição): todos.
- URGÊNCIA (cartões de opção): todos, quando a ordem é (ou vai ser) uma solicitação.
  A Ordem de Serviço aberta pela manutenção não tem urgência (o serviço não aceita
  esse campo), então a seção não aparece nela.
- PLANEJAMENTO (tipo, prioridade, tempo previsto) e ITENS DE CUSTO: manutenção e
  administrador.
- CONCLUSÃO (realizado, nota para o solicitante): em execução, para quem pode concluir;
  ou só leitura depois de concluída (para o usuario, só a nota).
Seção que o papel não usa não é desenhada, e o dado dela nem é pedido ao serviço.
Os números são a posição na lista (1, 2, 3...).
"""

from __future__ import annotations

from osapp.services import status as _status

SOLICITACAO = "solicitacao"
URGENCIA = "urgencia"
PLANEJAMENTO = "planejamento"
ITENS = "itens"
CONCLUSAO = "conclusao"

TITULOS = {
    SOLICITACAO: "Solicitação",
    URGENCIA: "Urgência",
    PLANEJAMENTO: "Planejamento",
    ITENS: "Itens de custo",
    CONCLUSAO: "Conclusão",
}

PAPEIS_DA_MANUTENCAO = ("manutencao", "admin")


def secoes(
    papel: str,
    status: str | None = None,
    solicitacao: bool = True,
    pode_concluir: bool = False,
) -> tuple[str, ...]:
    """Seções visíveis, em ordem. ``status`` None = ordem ainda não criada."""
    lista = [SOLICITACAO]
    if solicitacao:
        lista.append(URGENCIA)
    if papel in PAPEIS_DA_MANUTENCAO:
        lista += [PLANEJAMENTO, ITENS]
    if status == _status.CONCLUIDA or (
        status == _status.EM_EXECUCAO and pode_concluir and papel in PAPEIS_DA_MANUTENCAO
    ):
        lista.append(CONCLUSAO)
    return tuple(lista)


def numero(lista: tuple[str, ...], secao: str) -> int:
    """Número exibido da seção (posição + 1)."""
    return lista.index(secao) + 1
