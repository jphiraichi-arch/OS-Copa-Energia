"""Fixtures compartilhadas. Cada teste recebe um banco novo.

Por padrão usa-se um SQLite temporário. Se OS_TEST_DATABASE_URL estiver definida, os
mesmos testes rodam nesse banco (ex.: PostgreSQL), que é esvaziado antes de cada teste.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import MetaData

from osapp import db

RAIZ = Path(__file__).resolve().parents[1]


def config_alembic() -> AlembicConfig:
    return AlembicConfig(str(RAIZ / "alembic.ini"))


@pytest.fixture
def banco_vazio(tmp_path, monkeypatch):
    """Aponta OS_DATABASE_URL para um banco sem tabelas e devolve a URL."""
    url = os.environ.get("OS_TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'teste.db'}"
    monkeypatch.setenv("OS_DATABASE_URL", url)
    db.reiniciar()
    if os.environ.get("OS_TEST_DATABASE_URL"):
        engine = db.obter_engine()
        existente = MetaData()
        existente.reflect(bind=engine)
        existente.drop_all(bind=engine)
    yield url
    db.reiniciar()


@pytest.fixture
def banco(banco_vazio):
    """Banco novo com o esquema criado pela migração (alembic upgrade head)."""
    command.upgrade(config_alembic(), "head")
    return banco_vazio
