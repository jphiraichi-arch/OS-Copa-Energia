"""Configuração do logging padrão a partir de OS_LOG_LEVEL."""

from __future__ import annotations

import logging

from osapp.config import carregar_config

FORMATO = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configurar_logging(nivel: str | None = None) -> None:
    """Configura o logging raiz. Sem argumento, usa OS_LOG_LEVEL (padrão INFO)."""
    logging.basicConfig(level=nivel or carregar_config().log_level, format=FORMATO)
