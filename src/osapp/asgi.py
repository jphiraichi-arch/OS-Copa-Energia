"""O app ASGI: o FastAPI do Flet, a rota /saude e o trabalhador da fila de e-mails.

Separado de osapp/main.py para poder ser importado sem efeitos colaterais (o main valida
a configuração e liga o logging ao ser importado).
"""

from __future__ import annotations

import logging

import flet.fastapi as flet_fastapi

from osapp import config, saude
from osapp.services import fila_email
from osapp.ui.marca import PASTA_ASSETS

logger = logging.getLogger(__name__)


def criar_app_asgi(main):
    """O app ASGI do Flet com o trabalhador da fila de e-mails (prompt 32).

    Igual ao que ``ft.run(main, export_asgi_app=True)`` monta (o FastAPI do Flet com o
    app montado em '/'), mais os ganchos on_startup/on_shutdown: o trabalhador sobe uma
    vez por processo, na partida do servidor — nunca no ``main()``, que roda uma vez por
    sessão de navegador. Ver docs/ESTADO.md, prompt 32.
    """
    if config.email_habilitado():
        trabalhador = fila_email.Trabalhador()
        ao_iniciar, ao_parar = [trabalhador.iniciar], [trabalhador.parar]
    else:
        # Prompt 46: e-mail desligado. O trabalhador nem é criado: nenhuma conexão, nenhum
        # log de erro de envio; só esta linha na partida.
        ao_iniciar, ao_parar = [_avisar_email_desligado], []
    asgi = flet_fastapi.FastAPI(
        on_startup=ao_iniciar,
        on_shutdown=ao_parar,
        # Sem /docs, /redoc e /openapi.json: o app não publica API.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    # Rotas próprias ANTES do app Flet, que responde a tudo em '/' (SPA).
    asgi.add_api_route("/saude", saude.rota_saude, methods=["GET", "HEAD"], include_in_schema=False)
    asgi.mount("/", flet_fastapi.app(main, assets_dir=str(PASTA_ASSETS), no_cdn=True))
    return asgi


def _avisar_email_desligado() -> None:
    logger.info(
        "E-mail desligado (OS_EMAIL_HABILITADO diferente de 1): nada é enviado nem "
        "enfileirado; erros graves ficam só no log."
    )
