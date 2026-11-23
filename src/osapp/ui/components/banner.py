"""Faixa (banner) no topo de cada tela principal.

Cartão arredondado na cor primária: ícone, título, subtítulo (o nome da filial) e, à
direita, um ou dois indicadores ('Abertas: 12'). No celular os indicadores vão para
baixo do título. Sem regra de negócio: os números chegam prontos (services.ordens.contadores).
"""

from __future__ import annotations

import flet as ft

from osapp.ui import theme


def _indicador(rotulo: str, valor: str) -> ft.Control:
    return ft.Container(
        bgcolor=theme.COR_INDICADOR_FAIXA,
        border_radius=theme.RAIO_BOTAO,
        padding=ft.Padding.symmetric(horizontal=12, vertical=6),
        content=ft.Text(
            f"{rotulo}: {valor}",
            color=theme.COR_SOBRE_PRIMARIO,
            size=theme.FONTE_SUBTITULO,
            weight=ft.FontWeight.BOLD,
            no_wrap=True,
        ),
    )


def banner(
    icone: ft.IconData,
    titulo: str,
    subtitulo: str = "",
    indicadores: list[tuple[str, str]] | None = None,
    celular: bool = False,
) -> ft.Container:
    """``indicadores``: até dois pares (rótulo, valor)."""
    texto = ft.Column(
        [
            ft.Text(
                titulo,
                color=theme.COR_SOBRE_PRIMARIO,
                size=theme.FONTE_SAUDACAO,
                weight=ft.FontWeight.BOLD,
            ),
            *(
                [ft.Text(subtitulo, color=theme.COR_SOBRE_PRIMARIO_SUAVE, size=theme.FONTE_CORPO)]
                if subtitulo
                else []
            ),
        ],
        spacing=2,
        expand=True,
    )
    cabeca = ft.Row(
        [ft.Icon(icone, color=theme.COR_DESTAQUE, size=theme.TAMANHO_ICONE + 8), texto],
        spacing=theme.ESPACO_M,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        expand=not celular,
    )
    caixas = [_indicador(r, v) for r, v in (indicadores or [])[:2]]
    if celular:
        conteudo: ft.Control = ft.Column(
            [cabeca, *([ft.Row(caixas, wrap=True, spacing=theme.ESPACO_P)] if caixas else [])],
            spacing=theme.ESPACO_P + 4,
        )
    else:
        conteudo = ft.Row(
            [cabeca, *caixas],
            spacing=theme.ESPACO_P,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
    return ft.Container(
        bgcolor=theme.COR_PRIMARIO,
        border_radius=theme.RAIO_CARTAO,
        padding=ft.Padding.symmetric(horizontal=theme.ESPACO_G, vertical=theme.ESPACO_M + 4),
        content=conteudo,
    )
