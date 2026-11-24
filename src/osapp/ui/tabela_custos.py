"""Tabela de custos (prompt 26): decide tabela ou cartões e monta os textos. Módulo puro.

Colunas Categoria | Previsto | Realizado | Diferença com proporções fixas 40/20/20/20,
iguais em todas as linhas. Nas linhas de categoria a Diferença tem só o valor e o
percentual ('+R$ 120,00 (+12%)') e uma etiqueta 'acima'/'abaixo'; as palavras 'Acima do
previsto', 'Abaixo do previsto' ou 'Igual ao previsto' só aparecem no Total. Abaixo de
600 px de largura: um cartão por categoria, com os mesmos valores, e o Total por último.
"""

from __future__ import annotations

from dataclasses import dataclass

from osapp import formatacao
from osapp.ui import historico

LARGURA_MIN_TABELA = 600  # igual a theme.LARGURA_CELULAR_MAX (há teste)
PROPORCOES = (4, 2, 2, 2)  # Categoria, Previsto, Realizado, Diferença
CABECALHO = ("Categoria", "Previsto", "Realizado", "Diferença")
SEM_VALOR = "—"


@dataclass(frozen=True)
class LinhaCusto:
    nome: str
    previsto: str
    realizado: str
    diferenca: str  # categoria: o valor com sinal; Total: o texto com as palavras
    etiqueta: str | None  # 'acima' / 'abaixo' (só em categoria)
    total: bool
    percentual: str | None = None  # categoria: '(+12%)', numa linha própria


def _valor_da_categoria(diferenca: int, percentual: float | None) -> str:
    """Linha 1 da Diferença: o valor com sinal; sem previsto, a frase inteira (prompt 31)."""
    if percentual is None:
        return historico.texto_diferenca_compacta(diferenca, None)
    return historico.valor_com_sinal(diferenca)


def _percentual(diferenca: int, percentual: float | None) -> str | None:
    """'(+12%)' da linha de categoria (o mesmo de texto_diferenca_compacta), ou None."""
    if percentual is None or diferenca == 0:
        return None
    return f"({formatacao.formatar_percentual(percentual, sinal=True)})"


def modo(largura: float | None) -> str:
    """'tabela' a partir de 600 px; 'cartoes' abaixo (ou sem largura conhecida)."""
    return "tabela" if (largura or 0) >= LARGURA_MIN_TABELA else "cartoes"


def linhas(resumo, com_realizado: bool) -> list[LinhaCusto]:
    """Uma linha por categoria e o Total por último (números do serviço)."""
    resultado = []
    for c in resumo.por_categoria:
        resultado.append(
            LinhaCusto(
                nome=c.categoria_nome,
                previsto=formatacao.formatar_brl(c.previsto_centavos),
                realizado=formatacao.formatar_brl(c.realizado_centavos)
                if com_realizado
                else SEM_VALOR,
                diferenca=_valor_da_categoria(c.diferenca_centavos, c.diferenca_percentual)
                if com_realizado
                else SEM_VALOR,
                etiqueta=historico.etiqueta_diferenca(c.diferenca_centavos)
                if com_realizado
                else None,
                total=False,
                percentual=_percentual(c.diferenca_centavos, c.diferenca_percentual)
                if com_realizado
                else None,
            )
        )
    resultado.append(
        LinhaCusto(
            nome="Total",
            previsto=formatacao.formatar_brl(resumo.total_previsto_centavos),
            realizado=formatacao.formatar_brl(resumo.total_realizado_centavos)
            if com_realizado
            else SEM_VALOR,
            diferenca=historico.texto_diferenca_valor(
                resumo.diferenca_centavos, resumo.diferenca_percentual
            )
            if com_realizado
            else SEM_VALOR,
            etiqueta=None,
            total=True,
        )
    )
    return resultado
