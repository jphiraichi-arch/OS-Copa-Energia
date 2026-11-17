"""Infraestrutura de banco: metadados, engine, fábrica de sessões e ``sessao()``."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, MetaData, create_engine, event, func, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from osapp.config import carregar_config

CONVENCAO_DE_NOMES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarativa de todos os modelos."""

    metadata = MetaData(naming_convention=CONVENCAO_DE_NOMES)


def _minusculas(valor):
    return valor.lower() if isinstance(valor, str) else valor


def _preparar_conexao_sqlite(conexao_dbapi, _registro) -> None:
    """Liga as chaves estrangeiras e troca lower() por uma versão que entende acentos.

    O lower() nativo do SQLite só converte ASCII; sem isto a busca sem diferenciar
    maiúsculas falharia em palavras como 'BALANÇA'.
    """
    conexao_dbapi.create_function("lower", 1, _minusculas, deterministic=True)
    cursor = conexao_dbapi.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def criar_engine(url: str) -> Engine:
    """Cria um engine para a URL. No SQLite, liga as chaves estrangeiras em cada conexão."""
    if url.startswith("sqlite"):
        engine = create_engine(url)
        event.listen(engine, "connect", _preparar_conexao_sqlite)
        return engine
    # Bancos em rede (PostgreSQL): testa a conexão antes de usar e a renova de tempos em
    # tempos, porque bancos de nuvem encerram conexões paradas.
    return create_engine(url, pool_pre_ping=True, pool_recycle=300)


_engine: Engine | None = None
_fabrica: sessionmaker[Session] | None = None


def obter_engine() -> Engine:
    """Engine único do processo, criado na primeira chamada a partir de OS_DATABASE_URL."""
    global _engine, _fabrica
    if _engine is None:
        _engine = criar_engine(carregar_config().database_url)
        _fabrica = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def obter_fabrica_de_sessoes() -> sessionmaker[Session]:
    obter_engine()
    assert _fabrica is not None
    return _fabrica


def reiniciar() -> None:
    """Descarta o engine atual; o próximo uso relê OS_DATABASE_URL. Usado pelos testes."""
    global _engine, _fabrica
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _fabrica = None


@contextmanager
def sessao() -> Iterator[Session]:
    """Sessão transacional: commit ao sair sem erro, rollback em caso de erro."""
    s = obter_fabrica_de_sessoes()()
    try:
        yield s
        s.commit()
    except BaseException:
        s.rollback()
        raise
    finally:
        s.close()


# Número fixo e arbitrário que identifica a trava de inicialização no PostgreSQL.
TRAVA_DE_INICIALIZACAO = 74_182_026


@contextmanager
def trava_de_inicializacao(engine: Engine) -> Iterator[None]:
    """Faz migração e seed rodarem um de cada vez quando várias instâncias sobem juntas.

    Usa uma trava consultiva do PostgreSQL (pg_advisory_lock), presa a uma conexão
    própria: a segunda instância espera a primeira terminar e então encontra tudo
    pronto. No SQLite (desenvolvimento, um processo só) não faz nada.
    """
    if engine.dialect.name != "postgresql":
        yield
        return
    with engine.connect() as conexao:
        conexao.execute(select(func.pg_advisory_lock(TRAVA_DE_INICIALIZACAO)))
        conexao.commit()
        try:
            yield
        finally:
            conexao.execute(select(func.pg_advisory_unlock(TRAVA_DE_INICIALIZACAO)))
            conexao.commit()
