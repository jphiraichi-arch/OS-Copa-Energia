"""Cabeçalho do app: barra grafite fina com voltar, logotipo e chip da filial."""

from __future__ import annotations

import flet as ft

from osapp.ui import marca, theme


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


def _logo_do_cabecalho() -> ft.Control:
    """Logotipo da empresa no cabeçalho escuro; o provisório só se o arquivo faltar."""
    if marca.logo_disponivel():
        return marca.logo(theme.ALTURA_LOGO_CABECALHO)
    return logo()


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
    mostrar_voltar: bool = True,
) -> ft.Control:
    """Barra superior fina: voltar, logotipo e o chip da filial (sem menu: a navegação
    fica na barra inferior, e Configurações e Sair ficam em Perfil)."""
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
    return ft.Container(
        bgcolor=theme.COR_BARRA,
        padding=ft.Padding.only(left=theme.ESPACO_P, right=theme.ESPACO_M, top=2, bottom=2),
        alignment=ft.Alignment.CENTER,
        content=ft.Container(
            max_width=theme.LARGURA_MAX_CONTEUDO,
            content=ft.Row(
                controls=[
                    ft.Row(
                        [
                            _botao_icone(
                                ft.Icons.ARROW_BACK, "Voltar", on_voltar, visivel=mostrar_voltar
                            ),
                            _logo_do_cabecalho(),
                        ],
                        spacing=theme.ESPACO_P // 2,
                        tight=True,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    chip_filial,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ),
    )
