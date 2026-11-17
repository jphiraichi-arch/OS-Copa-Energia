"""Cabeçalho do app: barra grafite com logo neutro, voltar, chip da filial e menu."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from osapp.ui import theme


def logo(
    cor_texto: str = theme.COR_SOBRE_CABECALHO, escala: float = 1.0, texto: str = "OS"
) -> ft.Control:
    """Logo provisório: um ícone e um texto. Será trocado pelo arquivo do logotipo."""
    return ft.Row(
        controls=[
            ft.Icon(
                ft.Icons.BUILD_CIRCLE_OUTLINED,
                color=theme.COR_DESTAQUE,
                size=theme.TAMANHO_ICONE_LOGO * escala,
            ),
            ft.Text(
                texto,
                color=cor_texto,
                size=theme.FONTE_LOGO * escala,
                weight=ft.FontWeight.BOLD,
            ),
        ],
        spacing=theme.ESPACO_P,
        tight=True,
    )


def _botao_icone(icone: ft.IconData, dica: str, on_click=None, visivel=True) -> ft.IconButton:
    return ft.IconButton(
        icon=icone,
        icon_color=theme.COR_SOBRE_CABECALHO,
        icon_size=theme.TAMANHO_ICONE,
        tooltip=dica,
        width=theme.ALVO_TOQUE_MIN,
        height=theme.ALVO_TOQUE_MIN,
        on_click=on_click,
        # Invisível mas ocupando o lugar, para a barra não mudar de forma.
        opacity=1 if visivel else 0,
        disabled=not visivel,
    )


def barra(
    codigo_filial: str = "F000",
    on_voltar=None,
    on_menu=None,
    itens_menu: list[tuple[str, ft.IconData, Callable]] | None = None,
    mostrar_voltar: bool = True,
    recuo_esquerda: int = 0,
) -> ft.Control:
    """A barra do cabeçalho. ``itens_menu`` é uma lista de (texto, ícone, ao_clicar).

    ``recuo_esquerda`` alinha o conteúdo da barra com a área ao lado do trilho lateral.
    """
    chip_filial = ft.Container(
        content=ft.Text(
            codigo_filial,
            color=theme.COR_SOBRE_DESTAQUE,
            size=theme.FONTE_CHIP,
            weight=ft.FontWeight.BOLD,
            no_wrap=True,
        ),
        bgcolor=theme.COR_DESTAQUE,
        border_radius=theme.RAIO_CHIP,
        padding=ft.Padding.symmetric(horizontal=12, vertical=6),
        tooltip="Filial",
    )
    if itens_menu:
        menu: ft.Control = ft.PopupMenuButton(
            icon=ft.Icons.MENU,
            icon_color=theme.COR_SOBRE_CABECALHO,
            icon_size=theme.TAMANHO_ICONE,
            tooltip="Menu",
            bgcolor=theme.COR_CARTAO,
            width=theme.ALVO_TOQUE_MIN,
            height=theme.ALVO_TOQUE_MIN,
            items=[
                ft.PopupMenuItem(
                    content=ft.Text(texto, color=theme.COR_TITULO, size=theme.FONTE_CORPO),
                    icon=ft.Icon(icone, color=theme.COR_TITULO),
                    height=theme.ALVO_TOQUE_MIN,
                    on_click=ao_clicar,
                )
                for texto, icone, ao_clicar in itens_menu
            ],
        )
    else:
        menu = _botao_icone(ft.Icons.MENU, "Menu", on_menu)
    acoes = ft.Row(
        controls=[
            _botao_icone(ft.Icons.ARROW_BACK, "Voltar", on_voltar, visivel=mostrar_voltar),
            chip_filial,
            menu,
        ],
        spacing=theme.ESPACO_P // 2,
        tight=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    return ft.Container(
        bgcolor=theme.COR_CABECALHO,
        padding=ft.Padding.only(
            left=theme.ESPACO_M + recuo_esquerda, right=theme.ESPACO_P, top=4, bottom=4
        ),
        alignment=ft.Alignment.CENTER,
        content=ft.Container(
            max_width=theme.LARGURA_MAX_CONTEUDO,
            content=ft.Row(
                controls=[logo(), acoes],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ),
    )


def saudacao(nome: str = "Visitante") -> ft.Control:
    """A linha 'Olá, [nome]' que fica abaixo da barra."""
    return ft.Container(
        alignment=ft.Alignment.CENTER,
        padding=ft.Padding.only(left=theme.ESPACO_M, right=theme.ESPACO_M, top=theme.ESPACO_M),
        content=ft.Container(
            max_width=theme.LARGURA_MAX_CONTEUDO,
            alignment=ft.Alignment.CENTER_LEFT,
            content=ft.Text(
                f"Olá, {nome}",
                color=theme.COR_TITULO,
                size=theme.FONTE_SAUDACAO,
                weight=ft.FontWeight.BOLD,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
            ),
        ),
    )


def cabecalho(
    nome: str = "Visitante",
    codigo_filial: str = "F000",
    on_voltar=None,
    on_menu=None,
) -> ft.Control:
    """Cabeçalho completo: a barra e, abaixo dela, a saudação 'Olá, [nome]'."""
    return ft.Column(
        controls=[barra(codigo_filial, on_voltar, on_menu), saudacao(nome)],
        spacing=0,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
