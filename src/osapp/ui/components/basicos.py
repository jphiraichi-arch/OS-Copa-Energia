"""Peças pequenas reutilizadas pelas telas. Todas as cores vêm de ui/theme.py."""

from __future__ import annotations

import flet as ft

from osapp.services import status as status_os
from osapp.ui import theme


def cartao(conteudo: ft.Control, on_click=None) -> ft.Container:
    return ft.Container(
        bgcolor=theme.COR_CARTAO,
        border_radius=theme.RAIO_CARTAO,
        padding=theme.ESPACO_M,
        shadow=ft.BoxShadow(blur_radius=12, color=theme.COR_SOMBRA, offset=ft.Offset(0, 2)),
        content=conteudo,
        on_click=on_click,
        ink=on_click is not None,
    )


def titulo(texto: str, tamanho: int = theme.FONTE_TITULO) -> ft.Text:
    return ft.Text(texto, color=theme.COR_TITULO, size=tamanho, weight=ft.FontWeight.BOLD)


def subtitulo(texto: str) -> ft.Text:
    return ft.Text(texto, color=theme.COR_SUBTITULO, size=theme.FONTE_SUBTITULO)


def texto(valor: str) -> ft.Text:
    return ft.Text(valor, color=theme.COR_TITULO, size=theme.FONTE_CORPO)


def campo_texto(rotulo: str, **opcoes) -> ft.TextField:
    """Campo de texto com rótulo (não só placeholder) e cores do tema."""
    return ft.TextField(
        label=rotulo,
        color=theme.COR_TITULO,
        bgcolor=theme.COR_CAMPO_FUNDO,
        filled=True,
        fill_color=theme.COR_CAMPO_FUNDO,
        border_color=theme.COR_CONTORNO,
        focused_border_color=theme.COR_BOTAO_PRIMARIO,
        border_radius=theme.RAIO_BOTAO,
        label_style=ft.TextStyle(color=theme.COR_SUBTITULO),
        text_size=theme.FONTE_CORPO,
        error_style=ft.TextStyle(color=theme.COR_ERRO, size=theme.FONTE_PEQUENA),
        error_max_lines=3,
        **opcoes,
    )


def botao_primario(rotulo: str, icone: ft.IconData | None = None, on_click=None) -> ft.Button:
    """Botão primário de largura total (dentro de uma coluna STRETCH)."""
    return ft.Button(
        content=rotulo,
        icon=icone,
        style=theme.estilo_botao_primario(),
        height=theme.ALTURA_BOTAO,
        on_click=on_click,
    )


def botao_secundario(rotulo: str, icone: ft.IconData | None = None, on_click=None):
    return ft.OutlinedButton(
        content=rotulo,
        icon=icone,
        style=theme.estilo_botao_secundario(),
        height=theme.ALTURA_BOTAO,
        on_click=on_click,
    )


def carregando() -> ft.Control:
    return ft.Container(
        alignment=ft.Alignment.CENTER,
        padding=theme.ESPACO_G,
        content=ft.ProgressRing(
            width=32, height=32, stroke_width=3, color=theme.COR_BOTAO_PRIMARIO
        ),
    )


def coluna(controles: list[ft.Control], espaco: int = theme.ESPACO_M) -> ft.Column:
    return ft.Column(
        controls=controles,
        spacing=espaco,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )


def selo_status(status: str) -> ft.Container:
    """Selo com o rótulo do status. A informação está no texto, não só na cor."""
    fundo, cor = theme.cores_status(status)
    return ft.Container(
        bgcolor=fundo,
        border_radius=theme.RAIO_CHIP,
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        content=ft.Text(
            status_os.rotulo(status),
            color=cor,
            size=theme.FONTE_PEQUENA,
            weight=ft.FontWeight.BOLD,
            no_wrap=True,
        ),
    )


def rotulo_valor(rotulo: str, valor: str) -> ft.Column:
    """Um par 'rótulo pequeno em cima, valor embaixo'."""
    return ft.Column(
        controls=[
            ft.Text(rotulo, color=theme.COR_SUBTITULO, size=theme.FONTE_PEQUENA),
            ft.Text(valor, color=theme.COR_TITULO, size=theme.FONTE_CORPO, selectable=True),
        ],
        spacing=2,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )


def mensagem_central(mensagem: str) -> ft.Container:
    return ft.Container(
        alignment=ft.Alignment.CENTER,
        padding=theme.ESPACO_G,
        content=ft.Text(
            mensagem,
            color=theme.COR_SUBTITULO,
            size=theme.FONTE_CORPO,
            text_align=ft.TextAlign.CENTER,
        ),
    )
