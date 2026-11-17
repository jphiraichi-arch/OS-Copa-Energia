"""Ponto de entrada do app Flet (web, executado no servidor).

Desenvolvimento:  python -m osapp.main
Produção (ASGI):  uvicorn osapp.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import sys

import flet as ft

from osapp.config import Config, ConfigError, carregar_config
from osapp.logs import configurar_logging
from osapp.ui.app import App
from osapp.ui.marca import PASTA_ASSETS

PORTA_DESENVOLVIMENTO = 8550

logger = logging.getLogger("osapp")


async def main(page: ft.Page) -> None:
    """Chamado pelo Flet uma vez para cada sessão de navegador."""
    await App(page, carregar_config()).iniciar()


def _iniciar() -> Config:
    """Valida a configuração antes de servir qualquer página; aborta com mensagem clara."""
    try:
        config = carregar_config()
    except ConfigError as exc:
        sys.exit(f"Erro de configuração: {exc}")
    configurar_logging(config.log_level)
    return config


if __name__ == "__main__":
    _iniciar()
    logger.info("Servidor de desenvolvimento em http://localhost:%d", PORTA_DESENVOLVIMENTO)
    ft.run(
        main,
        view=ft.AppView.WEB_BROWSER,
        port=PORTA_DESENVOLVIMENTO,
        assets_dir=str(PASTA_ASSETS),
    )
else:
    # Importado por um servidor ASGI (uvicorn, hypercorn, gunicorn...).
    _iniciar()
    app = ft.run(main, export_asgi_app=True, assets_dir=str(PASTA_ASSETS))
