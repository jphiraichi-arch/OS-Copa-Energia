"""Fonte única de cores, raios e tamanhos da interface.

Nenhum valor hexadecimal de cor pode aparecer em outro arquivo de src/osapp
(há um teste que garante isso). Os valores são estimativas e mudam só aqui.
"""

from __future__ import annotations

import flet as ft

# --- Cores -----------------------------------------------------------------
# Tokens da decisão de 21/11/2026 (estimativas a partir de fotos; mudam só aqui).
COR_PRIMARIO = "#2F4A54"  # faixa (banner) e botões primários
COR_SOBRE_PRIMARIO = "#FFFFFF"
COR_SOBRE_PRIMARIO_SUAVE = "#D7E0E3"  # subtítulo dentro da faixa
COR_INDICADOR_FAIXA = "#24393F"  # fundo dos indicadores dentro da faixa
COR_DESTAQUE = "#F28C28"  # seleção, bordas de destaque, ícones (nunca texto pequeno)
COR_SOBRE_DESTAQUE = "#1F2A44"
COR_BARRA = "#3A3A3A"  # barra inferior e barra superior fina
COR_SOBRE_BARRA = "#FFFFFF"
COR_ICONE_BARRA = "#E5E7EB"  # ícones não selecionados na barra
COR_FUNDO_PAGINA = "#F1F2F4"
COR_CARTAO = "#FFFFFF"
COR_TITULO = "#1F2A44"
# Texto secundário: #6B7280 dá 4,3:1 sobre #F1F2F4 (reprova); este passa nos dois fundos.
COR_SUBTITULO = "#5F6673"
COR_CONTORNO = "#D5D8DD"
COR_ERRO = "#B3261E"
COR_SOBRE_ERRO = "#FFFFFF"
COR_SOMBRA = "#14000000"  # preto com ~8% de opacidade (AARRGGBB)
COR_FUNDO_LOGO = "#FFFFFF"  # placa clara: o logotipo tem letras escuras
COR_SELECAO_SUAVE = "#FCE3C5"  # fundo de chip selecionado
COR_CAMPO_FUNDO = "#FFFFFF"
COR_AVISO_FUNDO = "#FFF4E5"
COR_AVISO_TEXTO = "#7A4A00"
# Nomes antigos, mantidos como sinônimos dos tokens acima.
COR_CABECALHO = COR_BARRA
COR_SOBRE_CABECALHO = COR_SOBRE_BARRA
COR_BOTAO_PRIMARIO = COR_PRIMARIO
COR_SOBRE_BOTAO_PRIMARIO = COR_SOBRE_PRIMARIO
COR_INDICADOR_NAVEGACAO = COR_SELECAO_SUAVE
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
# Pontos e bordas de urgência (sempre ao lado do texto; nunca o único sinal).
COR_PONTO_URGENCIA = {
    "baixa": "#2E9E5B",  # verde
    "media": "#E3B505",  # amarelo
    "alta": "#E8590C",  # laranja
    "emergencial": "#C62828",  # vermelho
}
COR_PONTO_NEUTRO = "#9CA3AF"

# --- Raios -----------------------------------------------------------------
RAIO_CARTAO = 16
RAIO_BOTAO = 12
RAIO_CHIP = 999
RAIO_LOGO = 8

# --- Tamanhos e espaçamentos -----------------------------------------------
ALVO_TOQUE_MIN = 48
ALTURA_BOTAO = 52
LARGURA_MAX_CONTEUDO = 1100
LARGURA_MAX_LOGIN = 420
LARGURA_CELULAR_MAX = 600  # abaixo disto: layout de celular (1 coluna)
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
    rotulo = ft.TextStyle(size=FONTE_PEQUENA, color=COR_SOBRE_BARRA)
    return ft.Theme(
        use_material3=True,
        navigation_bar_theme=ft.NavigationBarTheme(
            bgcolor=COR_BARRA,
            indicator_color=COR_DESTAQUE,
            label_text_style={
                ft.ControlState.DEFAULT: rotulo,
                ft.ControlState.SELECTED: ft.TextStyle(
                    size=FONTE_PEQUENA, color=COR_SOBRE_BARRA, weight=ft.FontWeight.BOLD
                ),
            },
        ),
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


def cor_ponto_urgencia(nivel: str | None) -> str:
    return COR_PONTO_URGENCIA.get(nivel, COR_PONTO_NEUTRO)


# --- Contraste (WCAG 2.x) ----------------------------------------------------


def _luminancia(cor: str) -> float:
    """Luminância relativa de '#RRGGBB' (ou '#AARRGGBB', ignorando o alfa)."""
    valor = cor.lstrip("#")
    if len(valor) == 8:
        valor = valor[2:]
    canais = [int(valor[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in canais]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contraste(cor1: str, cor2: str) -> float:
    """Razão de contraste WCAG entre duas cores (1 a 21)."""
    clara, escura = sorted((_luminancia(cor1), _luminancia(cor2)), reverse=True)
    return (clara + 0.05) / (escura + 0.05)


CONTRASTE_MIN = 4.5  # WCAG AA para texto normal

# Todo par texto/fundo que as telas usam. O teste exige CONTRASTE_MIN em cada um.
PARES_TEXTO: dict[str, tuple[str, str]] = {
    "título sobre cartão": (COR_TITULO, COR_CARTAO),
    "título sobre fundo": (COR_TITULO, COR_FUNDO_PAGINA),
    "secundário sobre cartão": (COR_SUBTITULO, COR_CARTAO),
    "secundário sobre fundo": (COR_SUBTITULO, COR_FUNDO_PAGINA),
    "texto sobre faixa": (COR_SOBRE_PRIMARIO, COR_PRIMARIO),
    "subtítulo da faixa": (COR_SOBRE_PRIMARIO_SUAVE, COR_PRIMARIO),
    "indicador da faixa": (COR_SOBRE_PRIMARIO, COR_INDICADOR_FAIXA),
    "texto do botão primário": (COR_SOBRE_PRIMARIO, COR_PRIMARIO),
    "botão secundário sobre cartão": (COR_PRIMARIO, COR_CARTAO),
    "botão secundário sobre fundo": (COR_PRIMARIO, COR_FUNDO_PAGINA),
    "texto sobre destaque": (COR_SOBRE_DESTAQUE, COR_DESTAQUE),
    "rótulo da barra": (COR_SOBRE_BARRA, COR_BARRA),
    "chip selecionado": (COR_TITULO, COR_SELECAO_SUAVE),
    "erro sobre cartão": (COR_ERRO, COR_CARTAO),
    "erro sobre fundo": (COR_ERRO, COR_FUNDO_PAGINA),
    "texto sobre erro": (COR_SOBRE_ERRO, COR_ERRO),
    "aviso": (COR_AVISO_TEXTO, COR_AVISO_FUNDO),
    "status aberta": COR_STATUS_ABERTA[::-1],
    "status em execução": COR_STATUS_EM_EXECUCAO[::-1],
    "status concluída": COR_STATUS_CONCLUIDA[::-1],
    "status cancelada": COR_STATUS_CANCELADA[::-1],
    "status outro": COR_STATUS_OUTRO[::-1],
    "nível baixa": COR_NIVEL_BAIXA[::-1],
    "nível média": COR_NIVEL_MEDIA[::-1],
    "nível alta": COR_NIVEL_ALTA[::-1],
    "nível emergencial": COR_NIVEL_EMERGENCIAL[::-1],
    "nível vazio": COR_NIVEL_VAZIO[::-1],
    "origem": COR_ORIGEM[::-1],
}
