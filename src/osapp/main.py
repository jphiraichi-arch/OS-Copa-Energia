"""Ponto de entrada do app Flet (web, executado no servidor).

Desenvolvimento:  python -m osapp.main
Produção (ASGI):  uvicorn osapp.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import os
import sys

import flet as ft
import flet.fastapi as flet_fastapi

from osapp import rede
from osapp.config import Config, ConfigError, carregar_config
from osapp.logs import configurar_logging
from osapp.services import fila_email, protecao_login
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
        protecao_login.validar_configuracao()  # OS_HMAC_SEGREDO e limites por IP
        rede.ler_redes(os.environ.get(rede.VARIAVEL_PROXIES))
    except (ConfigError, ValueError) as exc:
        sys.exit(f"Erro de configuração: {exc}")
    configurar_logging(config.log_level)
    return config


def criar_app_asgi():
    """O app ASGI do Flet com o trabalhador da fila de e-mails (prompt 32).

    Igual ao que ``ft.run(main, export_asgi_app=True)`` monta (o FastAPI do Flet com o
    app montado em '/'), mais os ganchos on_startup/on_shutdown: o trabalhador sobe uma
    vez por processo, na partida do servidor — nunca no ``main()``, que roda uma vez por
    sessão de navegador. Ver docs/ESTADO.md, prompt 32.
    """
    trabalhador = fila_email.Trabalhador()
    asgi = flet_fastapi.FastAPI(on_startup=[trabalhador.iniciar], on_shutdown=[trabalhador.parar])
    asgi.mount("/", flet_fastapi.app(main, assets_dir=str(PASTA_ASSETS), no_cdn=True))
    return asgi


if __name__ == "__main__":
    _iniciar()
    logger.info("Servidor de desenvolvimento em http://localhost:%d", PORTA_DESENVOLVIMENTO)
    ft.run(
        main,
        view=ft.AppView.WEB_BROWSER,
        port=PORTA_DESENVOLVIMENTO,
        assets_dir=str(PASTA_ASSETS),
        no_cdn=True,
    )
else:
    # Importado por um servidor ASGI (uvicorn, hypercorn, gunicorn...).
    _iniciar()
    protecao_login.limpeza_ao_iniciar()
    # O IP do cliente é resolvido aqui (True-Client-Ip, X-Forwarded-For da direita para
    # a esquerda), só para conexões vindas de OS_PROXIES_CONFIAVEIS; ver osapp/rede.py.
    app = rede.ResolverIpCliente(criar_app_asgi())
