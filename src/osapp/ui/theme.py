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
COR_NAVEGACAO = "#FFFFFF"
COR_FUNDO_LOGO = "#FFFFFF"  # placa clara: o logotipo tem letras escuras
COR_INDICADOR_NAVEGACAO = "#FCE3C5"
COR_CAMPO_FUNDO = "#FFFFFF"
COR_DESABILITADO = "#9CA3AF"
COR_FUNDO_DESABILITADO = "#E5E7EB"
COR_AVISO_FUNDO = "#FFF4E5"
COR_AVISO_TEXTO = "#7A4A00"
# Selos de status: (fundo, texto). O texto do selo sempre acompanha a cor.
COR_STATUS_ABERTA = ("#E0ECFF", "#1D4ED8")
COR_STATUS_EM_EXECUCAO = ("#FFEDD5", "#9A3412")
COR_STATUS_CONCLUIDA = ("#DCFCE7", "#166534")
COR_STATUS_CANCELADA = ("#F3F4F6", "#4B5563")
COR_STATUS_OUTRO = ("#E5E7EB", "#374151")
# Urgência e prioridade (fundo, texto). Emergencial: fundo vermelho cheio, texto branco.
COR_NIVEL_BAIXA = ("#ECFDF5", "#065F46")
COR_NIVEL_MEDIA = ("#FEF9C3", "#713F12")
COR_NIVEL_ALTA = ("#FFEDD5", "#9A3412")
COR_NIVEL_EMERGENCIAL = ("#B3261E", "#FFFFFF")
COR_NIVEL_VAZIO = ("#F3F4F6", "#4B5563")
COR_ORIGEM = ("#EEF2FF", "#3730A3")

# --- Raios -----------------------------------------------------------------
RAIO_CARTAO = 16
RAIO_BOTAO = 12
RAIO_CHIP = 999
RAIO_LOGO = 8

# --- Tamanhos e espaçamentos -----------------------------------------------
ALVO_TOQUE_MIN = 48
ALTURA_BOTAO = 52
LARGURA_MAX_CONTEUDO = 720
LARGURA_MAX_LOGIN = 420
LARGURA_TRILHO = 100  # cabe 'Nova Ordem / de Serviço' em duas linhas
LARGURA_TRILHO_MIN = 600  # a partir daqui: trilho lateral em vez da barra inferior
ESPACO_P = 8
ESPACO_M = 16
ESPACO_G = 24
TAMANHO_ICONE = 24
TAMANHO_ICONE_LOGO = 28
# Alturas do logotipo. O arquivo tem 94 px de altura: acima de ~47 px de tela, telas
# de alta densidade ampliam a imagem e ela perde nitidez.
ALTURA_LOGO_CABECALHO = 30
ALTURA_LOGO_LOGIN = 56

# --- Tipografia ------------------------------------------------------------
# Fonte embutida no app (src/osapp/assets/fonts, licença SIL OFL 1.1): o texto não
# depende de baixar fontes de uma CDN. Roboto estática, latim + Latim Estendido-A.
FONTE_FAMILIA = "Roboto Copa"
FONTE_ARQUIVOS = {FONTE_FAMILIA: "/fonts/Roboto-Regular.ttf"}
FONTE_SAUDACAO = 22
FONTE_TITULO = 18
FONTE_SUBTITULO = 14
FONTE_BOTAO = 16
FONTE_LOGO = 20
FONTE_CHIP = 14
FONTE_CORPO = 16
FONTE_PEQUENA = 13


def criar_tema() -> ft.Theme:
    """Tema Material 3 com todas as cores usadas pelo app definidas explicitamente.

    O Flet 1.1 passou a usar superfícies neutras por padrão; por isso nada aqui
    depende das cores derivadas automaticamente.
    """
    return ft.Theme(
        use_material3=True,
        font_family=FONTE_FAMILIA,
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
    page.fonts = dict(FONTE_ARQUIVOS)
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


def estilo_botao_secundario() -> ft.ButtonStyle:
    """Botão de contorno, para ações secundárias."""
    return ft.ButtonStyle(
        color=COR_BOTAO_PRIMARIO,
        icon_color=COR_BOTAO_PRIMARIO,
        icon_size=TAMANHO_ICONE,
        text_style=ft.TextStyle(size=FONTE_BOTAO, weight=ft.FontWeight.BOLD),
        shape=ft.RoundedRectangleBorder(radius=RAIO_BOTAO),
        side=ft.BorderSide(width=1.5, color=COR_BOTAO_PRIMARIO),
        padding=ft.Padding.symmetric(horizontal=ESPACO_M),
    )


def estilo_botao_texto() -> ft.ButtonStyle:
    return ft.ButtonStyle(
        color=COR_BOTAO_PRIMARIO,
        text_style=ft.TextStyle(size=FONTE_BOTAO, weight=ft.FontWeight.BOLD),
    )


def cores_status(status: str) -> tuple[str, str]:
    """(fundo, texto) do selo de um status; status desconhecido usa um par neutro."""
    return {
        "ABERTA": COR_STATUS_ABERTA,
        "EM_EXECUCAO": COR_STATUS_EM_EXECUCAO,
        "CONCLUIDA": COR_STATUS_CONCLUIDA,
        "CANCELADA": COR_STATUS_CANCELADA,
    }.get(status, COR_STATUS_OUTRO)


def cores_nivel(nivel: str | None) -> tuple[str, str]:
    """(fundo, texto) do selo de urgência ou prioridade."""
    return {
        "baixa": COR_NIVEL_BAIXA,
        "media": COR_NIVEL_MEDIA,
        "alta": COR_NIVEL_ALTA,
        "emergencial": COR_NIVEL_EMERGENCIAL,
    }.get(nivel, COR_NIVEL_VAZIO)
