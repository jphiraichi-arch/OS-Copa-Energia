"""Tabela de custos (tela larga) ou cartões por categoria (celular). Sem regra de negócio:
os textos vêm de ui/tabela_custos.py, a partir do resumo calculado pelo serviço."""

from __future__ import annotations

import flet as ft

from osapp.ui import tabela_custos as tc
from osapp.ui import theme
from osapp.ui.components import basicos


def _etiqueta(texto: str | None) -> ft.Control:
    """Etiqueta pequena com texto ('acima'/'abaixo'): a cor nunca é o único sinal."""
    if not texto:
        return ft.Container()
    fundo, cor = theme.COR_STATUS_EM_EXECUCAO if texto == "acima" else theme.COR_STATUS_CONCLUIDA
    return ft.Row(
        [
            ft.Container(
                bgcolor=fundo,
                border_radius=theme.RAIO_CHIP,
                padding=ft.Padding.symmetric(horizontal=6, vertical=1),
                content=ft.Text(
                    texto, color=cor, size=theme.FONTE_PEQUENA, weight=ft.FontWeight.BOLD
                ),
            )
        ],
        tight=True,
    )


def _valor(texto: str, direita: bool = True) -> ft.Text:
    return ft.Text(
        texto,
        color=theme.COR_TITULO,
        size=theme.FONTE_SUBTITULO,
        no_wrap=True,
        text_align=ft.TextAlign.RIGHT if direita else ft.TextAlign.LEFT,
    )


def _celula(texto: str, proporcao: int, numerica: bool, negrito: bool) -> ft.Control:
    return ft.Text(
        texto,
        color=theme.COR_TITULO,
        size=theme.FONTE_SUBTITULO,
        weight=ft.FontWeight.BOLD if negrito else ft.FontWeight.NORMAL,
        expand=proporcao,
        # Valor numa linha só; o nome da categoria é que quebra se faltar espaço.
        no_wrap=numerica,
        text_align=ft.TextAlign.RIGHT if numerica else ft.TextAlign.LEFT,
    )


def _linha_tabela(linha, cabecalho: bool = False) -> ft.Control:
    nome, previsto, realizado, diferenca = (
        tc.CABECALHO
        if cabecalho
        else (linha.nome, linha.previsto, linha.realizado, linha.diferenca)
    )
    negrito = cabecalho or linha.total
    p = tc.PROPORCOES
    celula_diferenca: ft.Control
    if cabecalho or linha.total or not linha.etiqueta:
        celula_diferenca = _celula(diferenca, p[3], True, negrito)
    else:
        # Categoria: valor e percentual, cada um numa linha só, e a etiqueta.
        celula_diferenca = ft.Column(
            [
                _valor(diferenca),
                *([_valor(linha.percentual)] if linha.percentual else []),
                _etiqueta(linha.etiqueta),
            ],
            spacing=2,
            expand=p[3],
            horizontal_alignment=ft.CrossAxisAlignment.END,
        )
    return ft.Row(
        [
            _celula(nome, p[0], False, negrito),
            _celula(previsto, p[1], True, negrito),
            _celula(realizado, p[2], True, negrito),
            celula_diferenca,
        ],
        vertical_alignment=ft.CrossAxisAlignment.START,
        spacing=theme.ESPACO_P,
    )


def _cartao(linha) -> ft.Control:
    destaque = linha.total
    return ft.Container(
        bgcolor=theme.COR_SELECAO_SUAVE if destaque else theme.COR_CAMPO_FUNDO,
        border=ft.Border.all(
            2 if destaque else 1, theme.COR_DESTAQUE if destaque else theme.COR_CONTORNO
        ),
        border_radius=theme.RAIO_BOTAO,
        padding=theme.ESPACO_P + 4,
        content=basicos.coluna(
            [
                basicos.titulo(linha.nome, theme.FONTE_CORPO),
                basicos.rotulo_valor("Previsto", linha.previsto, uma_linha=True),
                basicos.rotulo_valor("Realizado", linha.realizado, uma_linha=True),
                basicos.rotulo_valor("Diferença", linha.diferenca, uma_linha=not linha.total),
                *([_valor(linha.percentual, direita=False)] if linha.percentual else []),
                *([_etiqueta(linha.etiqueta)] if linha.etiqueta else []),
            ],
            espaco=theme.ESPACO_P,
        ),
    )


def tabela_custos(resumo, com_realizado: bool, largura: float | None) -> ft.Control:
    linhas = tc.linhas(resumo, com_realizado)
    if tc.modo(largura) == "cartoes":
        return basicos.coluna([_cartao(linha) for linha in linhas], espaco=theme.ESPACO_P)
    corpo: list[ft.Control] = [_linha_tabela(None, cabecalho=True)]
    for linha in linhas:
        corpo.append(ft.Divider(height=1, thickness=1, color=theme.COR_CONTORNO))
        corpo.append(_linha_tabela(linha))
    return basicos.coluna(corpo, espaco=theme.ESPACO_P)
