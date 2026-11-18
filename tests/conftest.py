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

# Segredo fictício só para os testes (o HMAC das tentativas de login precisa de um).
SEGREDO_DE_TESTE = "segredo-de-teste-" + "x" * 32


@pytest.fixture(autouse=True)
def _segredo_hmac(monkeypatch):
    monkeypatch.setenv("OS_HMAC_SEGREDO", SEGREDO_DE_TESTE)


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


@pytest.fixture
def cenario(banco):
    """Duas filiais e seis usuários fictícios (sem calcular hash, para ser rápido).

    Devolve os ids: f1, f2, admin, marina, joao, pedro (F001), carlos (F002) e
    inativa (F001, desativada).
    """
    from osapp.db import sessao
    from tests.fabricas import nova_filial, novo_usuario

    with sessao() as s:
        f1 = nova_filial(s, "F001", "Filial Modelo Norte")
        f2 = nova_filial(s, "F002", "Filial Modelo Sul")
        usuarios = {
            "admin": novo_usuario(s, f1, "admin", "Administrador Fictício", is_admin=True),
            "marina": novo_usuario(s, f1, "marina.teste", "Marina Teste"),
            "joao": novo_usuario(s, f1, "joao.ficticio", "João Fictício"),
            "pedro": novo_usuario(s, f1, "pedro.modelo", "Pedro Modelo"),
            "carlos": novo_usuario(s, f2, "carlos.exemplo", "Carlos Exemplo"),
            "inativa": novo_usuario(s, f1, "ines.inativa", "Inês Inativa", ativo=False),
        }
        return {"f1": f1.id, "f2": f2.id, **{k: u.id for k, u in usuarios.items()}}
