"""Fonte única de cores, raios e tamanhos da interface.

Nenhum valor hexadecimal de cor pode aparecer em outro arquivo de src/osapp
(há um teste que garante isso). Os valores são estimativas e mudam só aqui.
"""

from __future__ import annotations

import flet as ft

# --- Cores -----------------------------------------------------------------
COR_CABECALHO = "#3A3A3A"
COR_SOBRE_CABECALHO = "#FFFFFF"
COR_DESTAQUE = "#F28C28"
COR_SOBRE_DESTAQUE = "#1F2A44"
COR_BOTAO_PRIMARIO = "#2F4A54"
COR_SOBRE_BOTAO_PRIMARIO = "#FFFFFF"
COR_FUNDO_PAGINA = "#F1F2F4"
COR_CARTAO = "#FFFFFF"
COR_TITULO = "#1F2A44"
COR_SUBTITULO = "#6B7280"
COR_CONTORNO = "#D5D8DD"
COR_ERRO = "#B3261E"
COR_SOBRE_ERRO = "#FFFFFF"
COR_SOMBRA = "#14000000"  # preto com ~8% de opacidade (AARRGGBB)

# --- Raios -----------------------------------------------------------------
RAIO_CARTAO = 16
RAIO_BOTAO = 12
RAIO_CHIP = 999

# --- Tamanhos e espaçamentos -----------------------------------------------
ALVO_TOQUE_MIN = 48
ALTURA_BOTAO = 52
LARGURA_MAX_CONTEUDO = 720
ESPACO_P = 8
ESPACO_M = 16
ESPACO_G = 24
TAMANHO_ICONE = 24
TAMANHO_ICONE_LOGO = 28

# --- Tipografia ------------------------------------------------------------
FONTE_SAUDACAO = 22
FONTE_TITULO = 18
FONTE_SUBTITULO = 14
FONTE_BOTAO = 16
FONTE_LOGO = 20
FONTE_CHIP = 14


def criar_tema() -> ft.Theme:
    """Tema Material 3 com todas as cores usadas pelo app definidas explicitamente.

    O Flet 1.1 passou a usar superfícies neutras por padrão; por isso nada aqui
    depende das cores derivadas automaticamente.
    """
    return ft.Theme(
        use_material3=True,
        scaffold_bgcolor=COR_FUNDO_PAGINA,
        color_scheme=ft.ColorScheme(
            primary=COR_BOTAO_PRIMARIO,
            on_primary=COR_SOBRE_BOTAO_PRIMARIO,
            secondary=COR_DESTAQUE,
            on_secondary=COR_SOBRE_DESTAQUE,
            error=COR_ERRO,
            on_error=COR_SOBRE_ERRO,
            surface=COR_CARTAO,
            on_surface=COR_TITULO,
            on_surface_variant=COR_SUBTITULO,
            outline=COR_CONTORNO,
            surface_tint=COR_CARTAO,
        ),
    )


def aplicar_tema(page: ft.Page) -> None:
    page.theme = criar_tema()
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = COR_FUNDO_PAGINA


def estilo_botao_primario() -> ft.ButtonStyle:
    return ft.ButtonStyle(
        color=COR_SOBRE_BOTAO_PRIMARIO,
        bgcolor=COR_BOTAO_PRIMARIO,
        icon_color=COR_SOBRE_BOTAO_PRIMARIO,
        icon_size=TAMANHO_ICONE,
        text_style=ft.TextStyle(size=FONTE_BOTAO, weight=ft.FontWeight.BOLD),
        shape=ft.RoundedRectangleBorder(radius=RAIO_BOTAO),
        padding=ft.Padding.symmetric(horizontal=ESPACO_M),
    )
