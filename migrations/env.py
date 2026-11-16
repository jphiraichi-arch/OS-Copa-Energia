"""Ambiente do Alembic. A URL vem de osapp.config (OS_DATABASE_URL), nunca do alembic.ini."""

from __future__ import annotations

from alembic import context

import osapp.models  # noqa: F401  (registra as tabelas em Base.metadata)
from osapp.config import carregar_config
from osapp.db import Base, criar_engine

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=carregar_config().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = criar_engine(carregar_config().database_url)
    try:
        with engine.connect() as conexao:
            context.configure(
                connection=conexao,
                target_metadata=target_metadata,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
