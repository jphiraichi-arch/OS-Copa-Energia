"""Ponto de entrada do app Flet (web, executado no servidor).

Desenvolvimento:  python -m osapp.main
Produção (ASGI):  uvicorn osapp.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import sys

import flet as ft

from osapp.config import Config, ConfigError, carregar_config
from osapp.ui import theme
from osapp.ui.components.cabecalho import cabecalho

PORTA_DESENVOLVIMENTO = 8550

logger = logging.getLogger("osapp")


def construir_conteudo_smoke() -> ft.Control:
    """Página de fumaça do prompt 1: cabeçalho, um cartão e um botão primário."""
    cartao = ft.Container(
        bgcolor=theme.COR_CARTAO,
        border_radius=theme.RAIO_CARTAO,
        padding=theme.ESPACO_M,
        shadow=ft.BoxShadow(blur_radius=12, color=theme.COR_SOMBRA, offset=ft.Offset(0, 2)),
        content=ft.Column(
            controls=[
                ft.Text(
                    "Sistema de OS",
                    color=theme.COR_TITULO,
                    size=theme.FONTE_TITULO,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(
                    "Página de teste do esqueleto do projeto. As telas reais chegam "
                    "nas próximas etapas.",
                    color=theme.COR_SUBTITULO,
                    size=theme.FONTE_SUBTITULO,
                ),
            ],
            spacing=theme.ESPACO_P,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        ),
    )
    botao = ft.Button(
        content="Nova ordem de serviço",
        icon=ft.Icons.ADD_CIRCLE_OUTLINE,
        style=theme.estilo_botao_primario(),
        height=theme.ALTURA_BOTAO,
    )
    corpo = ft.Container(
        alignment=ft.Alignment.TOP_CENTER,
        padding=theme.ESPACO_M,
        content=ft.Container(
            max_width=theme.LARGURA_MAX_CONTEUDO,
            content=ft.Column(
                controls=[cartao, botao],
                spacing=theme.ESPACO_M,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        ),
    )
    return ft.Column(
        controls=[cabecalho(nome="Visitante", codigo_filial="F000"), corpo],
        spacing=0,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )


def main(page: ft.Page) -> None:
    page.title = "Sistema de OS"
    theme.aplicar_tema(page)
    page.padding = 0
    page.spacing = 0
    page.scroll = ft.ScrollMode.AUTO
    page.horizontal_alignment = ft.CrossAxisAlignment.STRETCH
    page.add(ft.SafeArea(content=construir_conteudo_smoke()))


def _iniciar() -> Config:
    """Valida a configuração antes de servir qualquer página; aborta com mensagem clara."""
    try:
        config = carregar_config()
    except ConfigError as exc:
        sys.exit(f"Erro de configuração: {exc}")
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return config


if __name__ == "__main__":
    _iniciar()
    logger.info("Servidor de desenvolvimento em http://localhost:%d", PORTA_DESENVOLVIMENTO)
    ft.run(main, view=ft.AppView.WEB_BROWSER, port=PORTA_DESENVOLVIMENTO)
else:
    # Importado por um servidor ASGI (uvicorn, hypercorn, gunicorn...).
    _iniciar()
    app = ft.run(main, export_asgi_app=True)
