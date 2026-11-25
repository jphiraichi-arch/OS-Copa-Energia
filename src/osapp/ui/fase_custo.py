"""Como mostrar uma fase de custo (prompt 41). Funções puras (testadas).

- Nenhum item e sem a marca: pill 'A DEFINIR' e total '—'. Nunca 'R$ 0,00' para 'não
  preenchido'.
- Marcada Sem gasto: pill e total 'SEM GASTO'.
- Com itens: o total em R$ (R$ 0,00 só quando os itens somam mesmo zero).
"""

from __future__ import annotations

from dataclasses import dataclass

from osapp import formatacao

A_DEFINIR = "A DEFINIR"
SEM_GASTO = "SEM GASTO"
TRACO = "—"


@dataclass(frozen=True)
class ExibicaoFase:
    pill: str
    total: str
    tom: str  # tom do status_pill: 'neutro', 'sucesso', 'info'


def exibicao(tem_itens: bool, sem_gasto: bool, total_centavos: int) -> ExibicaoFase:
    if tem_itens:
        texto = formatacao.formatar_brl(total_centavos)
        return ExibicaoFase(texto, texto, "info")
    if sem_gasto:
        return ExibicaoFase(SEM_GASTO, SEM_GASTO, "sucesso")
    return ExibicaoFase(A_DEFINIR, TRACO, "neutro")


def texto_da_lista(tem_itens: bool, sem_gasto: bool, total_centavos: int) -> str:
    """Cartão da lista: '—', 'Sem gasto' ou o total."""
    if tem_itens:
        return formatacao.formatar_brl(total_centavos)
    return "Sem gasto" if sem_gasto else TRACO
