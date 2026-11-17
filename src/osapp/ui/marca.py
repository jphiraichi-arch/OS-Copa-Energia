"""Logotipo da Copa Energia: arquivo, pasta servida pelo Flet e controle pronto.

Usa somente o arquivo do repositório (src/osapp/assets/logo.png), sem redesenhar nem
recolorir. Como o logotipo tem letras escuras, no cabeçalho escuro ele vai sobre uma
placa clara. Se o arquivo faltar, as telas usam o logo provisório.
"""

from __future__ import annotations

from pathlib import Path

import flet as ft

from osapp.ui import textos, theme

# Caminho absoluto: no contêiner o pacote é instalado fora de src/, e o Flet resolve
# caminhos relativos a partir da pasta de trabalho.
PASTA_ASSETS = Path(__file__).resolve().parents[1] / "assets"
ARQUIVO_LOGO = "logo.png"


def logo_disponivel() -> bool:
    return (PASTA_ASSETS / ARQUIVO_LOGO).is_file()


def logo(altura: int) -> ft.Control:
    """O logotipo na altura pedida, proporções mantidas, sobre uma placa clara."""
    return ft.Container(
        bgcolor=theme.COR_FUNDO_LOGO,
        border_radius=theme.RAIO_LOGO,
        padding=ft.Padding.symmetric(horizontal=theme.ESPACO_P, vertical=3),
        content=ft.Image(
            src=ARQUIVO_LOGO,
            height=altura,
            fit=ft.BoxFit.CONTAIN,
            filter_quality=ft.FilterQuality.HIGH,
            semantics_label=textos.MARCA_ROTULO,
        ),
        tooltip=textos.MARCA_ROTULO,
    )
