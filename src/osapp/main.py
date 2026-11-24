"""Ponto de entrada do app Flet (web, executado no servidor).

Desenvolvimento:  python -m osapp.main
Produção (ASGI):  uvicorn osapp.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import sys

import flet as ft

from osapp import config as config_mod
from osapp import rede
from osapp.asgi import criar_app_asgi
from osapp.config import Config, ConfigError, carregar_config
from osapp.logs import configurar_logging
from osapp.services import alertas, protecao_login
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
        rede.ler_redes(config_mod.proxies_confiaveis())
    except (ConfigError, ValueError) as exc:
        sys.exit(f"Erro de configuração: {exc}")
    configurar_logging(config.log_level)
    alertas.instalar()  # prompt 33: ERROR/CRITICAL viram alerta (com limites)
    return config


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
    # O IP do cliente é resolvido aqui (cabeçalho de OS_CABECALHO_IP_CLIENTE, se houver;
    # X-Forwarded-For da direita para a esquerda), só para conexões vindas de
    # OS_PROXIES_CONFIAVEIS; ver osapp/rede.py.
    app = rede.ResolverIpCliente(criar_app_asgi(main))
