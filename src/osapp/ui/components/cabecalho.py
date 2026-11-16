"""Cabeçalho do app: barra grafite com logo neutro, voltar, chip da filial e menu."""

from __future__ import annotations

import flet as ft

from osapp.ui import theme


def _botao_icone(icone: ft.IconData, dica: str, on_click=None) -> ft.IconButton:
    return ft.IconButton(
        icon=icone,
        icon_color=theme.COR_SOBRE_CABECALHO,
        icon_size=theme.TAMANHO_ICONE,
        tooltip=dica,
        width=theme.ALVO_TOQUE_MIN,
        height=theme.ALVO_TOQUE_MIN,
        on_click=on_click,
    )


def cabecalho(
    nome: str = "Visitante",
    codigo_filial: str = "F000",
    on_voltar=None,
    on_menu=None,
) -> ft.Control:
    """Devolve o cabeçalho completo: a barra e, abaixo dela, a saudação 'Olá, [nome]'."""
    logo = ft.Row(
        controls=[
            ft.Icon(
                ft.Icons.BUILD_CIRCLE_OUTLINED,
                color=theme.COR_DESTAQUE,
                size=theme.TAMANHO_ICONE_LOGO,
            ),
            ft.Text(
                "OS",
                color=theme.COR_SOBRE_CABECALHO,
                size=theme.FONTE_LOGO,
                weight=ft.FontWeight.BOLD,
            ),
        ],
        spacing=theme.ESPACO_P,
        tight=True,
    )
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
    acoes = ft.Row(
        controls=[
            _botao_icone(ft.Icons.ARROW_BACK, "Voltar", on_voltar),
            chip_filial,
            _botao_icone(ft.Icons.MENU, "Menu", on_menu),
        ],
        spacing=theme.ESPACO_P // 2,
        tight=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    barra = ft.Container(
        bgcolor=theme.COR_CABECALHO,
        padding=ft.Padding.only(left=theme.ESPACO_M, right=theme.ESPACO_P, top=4, bottom=4),
        alignment=ft.Alignment.CENTER,
        content=ft.Container(
            max_width=theme.LARGURA_MAX_CONTEUDO,
            content=ft.Row(
                controls=[logo, acoes],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ),
    )
    saudacao = ft.Container(
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
    return ft.Column(
        controls=[barra, saudacao],
        spacing=0,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
