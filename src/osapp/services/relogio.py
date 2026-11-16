"""Relógio da aplicação. Chame sempre ``relogio.agora()`` para que os testes possam trocá-lo."""

from __future__ import annotations

from datetime import UTC, datetime


def agora() -> datetime:
    """Instante atual em UTC, com fuso."""
    return datetime.now(UTC)
