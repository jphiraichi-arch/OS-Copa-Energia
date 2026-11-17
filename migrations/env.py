"""Ambiente do Alembic. A URL vem de osapp.config (OS_DATABASE_URL), nunca do alembic.ini."""

from __future__ import annotations

from alembic import context

import osapp.models  # noqa: F401  (registra as tabelas em Base.metadata)
from osapp.config import carregar_config
from osapp.db import Base, criar_engine, trava_de_inicializacao

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
        # Instâncias que sobem juntas migram uma de cada vez (ver db.trava_de_inicializacao).
        with trava_de_inicializacao(engine), engine.connect() as conexao:
            sqlite = conexao.dialect.name == "sqlite"
            if sqlite:
                # No SQLite, alterar uma coluna recria a tabela (modo batch). Com as chaves
                # estrangeiras ligadas, apagar a tabela antiga falha quando outras tabelas
                # apontam para ela. Desliga-se a verificação durante a migração (precisa ser
                # fora de transação) e confere-se a integridade no fim.
                conexao.exec_driver_sql("PRAGMA foreign_keys=OFF")
                conexao.commit()
            context.configure(
                connection=conexao,
                target_metadata=target_metadata,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
            if sqlite:
                violacoes = conexao.exec_driver_sql("PRAGMA foreign_key_check").all()
                conexao.exec_driver_sql("PRAGMA foreign_keys=ON")
                conexao.commit()
                if violacoes:
                    raise RuntimeError(
                        f"Migração deixou {len(violacoes)} referência(s) inválida(s)."
                    )
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
