"""Prompt 36: backup criptografado e restauração (scripts/backup.py, scripts/restaurar.py).

Os testes de ida e volta precisam de PostgreSQL (OS_TEST_DATABASE_URL), pg_dump/pg_restore
e age instalados; sem eles são pulados (docs/BACKUP.md traz os comandos).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.conftest import RAIZ

sys.path.insert(0, str(RAIZ / "scripts"))

import backup  # noqa: E402
import restaurar  # noqa: E402

T0 = datetime(2026, 11, 24, 6, 0, tzinfo=UTC)
FERRAMENTAS = all(shutil.which(c) for c in ("pg_dump", "pg_restore", "psql", "age", "age-keygen"))
URL_TESTE = os.environ.get("OS_TEST_DATABASE_URL")
precisa_pg = pytest.mark.skipif(
    not (FERRAMENTAS and URL_TESTE),
    reason="precisa de OS_TEST_DATABASE_URL, pg_dump, pg_restore, psql e age",
)


# --- Funções puras ---------------------------------------------------------------------------


def test_nome_por_data_utc():
    assert backup.nome_do_backup(T0) == "os-20261124T060000Z.dump.age"
    assert backup.data_do_nome("os-20261124T060000Z.dump.age") == T0
    assert backup.data_do_nome("outra-coisa.txt") is None


def _nomes(*dias_atras, sem_manifesto=()):
    nomes = []
    for d in dias_atras:
        nome = backup.nome_do_backup(T0 - timedelta(days=d))
        nomes.append(nome)
        if d not in sem_manifesto:
            nomes.append(nome + backup.SUFIXO_MANIFESTO)
    return nomes


def test_retencao_apaga_so_os_velhos():
    nomes = _nomes(0, 10, 29, 31, 45)
    apagar = backup.a_apagar(nomes, T0, 30)
    assert sorted(apagar) == sorted(_nomes(31, 45))


def test_retencao_nunca_apaga_o_mais_recente_bem_sucedido():
    # Todos velhos; o mais novo (40 dias) não tem manifesto (falhou): protege o de 50.
    nomes = _nomes(40, 50, 60, sem_manifesto=(40,))
    apagar = backup.a_apagar(nomes, T0, 30)
    protegido = backup.nome_do_backup(T0 - timedelta(days=50))
    assert protegido not in apagar and protegido + backup.SUFIXO_MANIFESTO not in apagar
    assert backup.nome_do_backup(T0 - timedelta(days=60)) in apagar
    assert backup.nome_do_backup(T0 - timedelta(days=40)) in apagar


def test_url_vai_para_variaveis_do_libpq():
    env = backup.ambiente_libpq(
        "postgresql+psycopg://os:s%40nha@db.exemplo:6543/os?sslmode=require"
    )
    assert env == {
        "PGHOST": "db.exemplo",
        "PGPORT": "6543",
        "PGDATABASE": "os",
        "PGUSER": "os",
        "PGPASSWORD": "s@nha",
        "PGSSLMODE": "require",
    }


def test_restaurar_recusa_producao_sem_flag_e_confirmacao():
    prod = "postgresql://u:x@db.exemplo:5432/os"
    mesma = "postgresql+psycopg://outro:y@db.exemplo:5432/os"
    with pytest.raises(backup.ErroBackup, match="PRODUÇÃO"):
        restaurar.exigir_autorizacao(mesma, prod, permitir=False)
    with pytest.raises(backup.ErroBackup, match="Confirmação"):
        restaurar.exigir_autorizacao(mesma, prod, permitir=True, ler=lambda _p: "sim")
    restaurar.exigir_autorizacao(mesma, prod, permitir=True, ler=lambda _p: "RESTAURAR PRODUCAO")
    restaurar.exigir_autorizacao("postgresql://u@db.exemplo:5432/copia", prod, permitir=False)


def test_mensagem_de_erro_sem_url():
    texto = backup._resumo(b'connection to "postgresql://u:senha@h/db" failed')
    assert "senha" not in texto and "<url>" in texto


def test_gitignore_cobre_backups_e_chaves():
    ignorado = (RAIZ / ".gitignore").read_text("utf-8")
    for padrao in ("*.dump", "*.dump.age", "*.manifest.json", "*.agekey"):
        assert padrao in ignorado


# --- Ida e volta (PostgreSQL + age) ----------------------------------------------------------


def _url_admin() -> str:
    base = URL_TESTE.rsplit("/", 1)[0]
    return base + "/postgres"


def _psql(url: str, sql: str) -> str:
    env = {**os.environ, **backup.ambiente_libpq(url)}
    return subprocess.run(
        ["psql", "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    ).stdout.strip()


@pytest.fixture
def bancos():
    origem = URL_TESTE.rsplit("/", 1)[0] + "/os_backup_origem"
    copia = URL_TESTE.rsplit("/", 1)[0] + "/os_backup_copia"
    for nome in ("os_backup_origem", "os_backup_copia"):
        _psql(_url_admin(), f"DROP DATABASE IF EXISTS {nome}")
        _psql(_url_admin(), f"CREATE DATABASE {nome}")
    yield origem, copia
    for nome in ("os_backup_origem", "os_backup_copia"):
        _psql(_url_admin(), f"DROP DATABASE IF EXISTS {nome} WITH (FORCE)")


@pytest.fixture
def chaves(tmp_path):
    privada = tmp_path / "chave.agekey"
    subprocess.run(["age-keygen", "-o", str(privada)], capture_output=True, check=True)
    publica = subprocess.run(
        ["age-keygen", "-y", str(privada)], capture_output=True, text=True, check=True
    ).stdout.strip()
    return publica, privada


def _povoar(url: str, monkeypatch) -> None:
    from alembic import command

    from osapp import db
    from osapp.services import administracao, ordens
    from tests.conftest import config_alembic

    monkeypatch.setenv("OS_DATABASE_URL", url)
    db.reiniciar()
    command.upgrade(config_alembic(), "head")
    administracao.criar_filial("1007", "Jardinópolis")
    uid = administracao.criar_usuario("Ana", "ana.admin", "senha-ficticia-123", "1007", True).id
    for i in range(5):
        ordens.criar_solicitacao(uid, f"Vazamento {i}", "Óleo no piso, ação já.", "alta")
    db.reiniciar()


TABELAS = ("usuarios", "ordens_servico", "os_eventos", "filiais", "alembic_version")


@precisa_pg
def test_backup_e_restauracao_ida_e_volta(bancos, chaves, tmp_path, monkeypatch):
    origem, copia = bancos
    publica, privada = chaves
    _povoar(origem, monkeypatch)
    pasta = tmp_path / "armazenamento"
    pasta.mkdir()
    monkeypatch.setenv("OS_DATABASE_URL", origem)
    monkeypatch.setenv("OS_BACKUP_CHAVE_PUBLICA", publica)
    resultado = backup.executar(backup.DestinoPasta(str(pasta)), agora=T0)
    arquivos = sorted(p.name for p in pasta.iterdir())
    assert arquivos == [resultado.nome, resultado.nome + backup.SUFIXO_MANIFESTO]
    conteudo = (pasta / resultado.nome).read_bytes()
    assert conteudo.startswith(b"age-encryption.org/v1") and b"Vazamento" not in conteudo
    assert not list(Path(os.environ.get("TMPDIR", "/tmp")).glob("os-backup-*"))  # limpou

    args = argparse.Namespace(
        arquivo="ultimo",
        identidade=str(privada),
        destino_url=copia,
        url_producao=origem,
        permitir_producao=False,
    )
    assert restaurar.executar(args, backup.DestinoPasta(str(pasta))) == resultado.nome
    for tabela in TABELAS:
        sql = f"SELECT count(*) FROM {tabela}"
        assert _psql(copia, sql) == _psql(origem, sql), tabela
    amostra = "SELECT numero, titulo, urgencia FROM ordens_servico ORDER BY id LIMIT 1"
    assert _psql(copia, amostra) == _psql(origem, amostra) != ""
    # O destino agora não está vazio: uma segunda restauração é recusada.
    with pytest.raises(backup.ErroBackup, match="vazio"):
        restaurar.executar(args, backup.DestinoPasta(str(pasta)))


@precisa_pg
def test_arquivo_corrompido_falha_no_sha_antes_de_decriptar(bancos, chaves, tmp_path, monkeypatch):
    origem, copia = bancos
    publica, privada = chaves
    _povoar(origem, monkeypatch)
    pasta = tmp_path / "armazenamento"
    pasta.mkdir()
    monkeypatch.setenv("OS_DATABASE_URL", origem)
    monkeypatch.setenv("OS_BACKUP_CHAVE_PUBLICA", publica)
    nome = backup.executar(backup.DestinoPasta(str(pasta)), agora=T0).nome
    dados = bytearray((pasta / nome).read_bytes())
    dados[-10] ^= 0xFF
    (pasta / nome).write_bytes(bytes(dados))
    chamado = []
    monkeypatch.setattr(restaurar, "restaurar", lambda *a: chamado.append(a))
    args = argparse.Namespace(
        arquivo=nome,
        identidade=str(privada),
        destino_url=copia,
        url_producao=origem,
        permitir_producao=False,
    )
    with pytest.raises(backup.ErroBackup, match="SHA-256"):
        restaurar.executar(args, backup.DestinoPasta(str(pasta)))
    assert chamado == []


@precisa_pg
def test_falha_do_pg_dump_sai_com_erro_e_nao_deixa_arquivo(tmp_path, chaves, monkeypatch):
    publica, _ = chaves
    pasta = tmp_path / "armazenamento"
    pasta.mkdir()
    monkeypatch.setenv("OS_DATABASE_URL", "postgresql://ninguem:x@127.0.0.1:1/nada")
    monkeypatch.setenv("OS_BACKUP_CHAVE_PUBLICA", publica)
    monkeypatch.setenv("OS_BACKUP_DESTINO", "pasta")
    monkeypatch.setenv("OS_BACKUP_BUCKET", str(pasta))
    monkeypatch.setattr(backup, "alertar_falha", lambda etapa: None)
    assert backup.main() == 1
    assert list(pasta.iterdir()) == []
