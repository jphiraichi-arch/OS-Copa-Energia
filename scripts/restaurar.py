#!/usr/bin/env python3
"""Restaura um backup criptografado do Sistema de OS num banco VAZIO (prompt 36).

    python scripts/restaurar.py --arquivo os-20261124T060000Z.dump.age \\
        --identidade /media/pendrive/os-backup.agekey \\
        --destino-url postgresql://os_dono:...@localhost:5432/os_restaurado

    --arquivo ultimo   escolhe o backup mais recente bem-sucedido.

Passos: baixa o backup e o manifesto do destino configurado (OS_BACKUP_DESTINO,
OS_BACKUP_BUCKET e as chaves de acesso, como no backup); confere o SHA-256 ANTES de
decriptar; decripta com a chave PRIVADA indicada na hora (nunca guardada pelo script) e
restaura com pg_restore no banco de --destino-url, que precisa estar vazio.

Recusa restaurar na URL de produção (OS_DATABASE_URL, ou --url-producao) sem
--permitir-producao E a confirmação digitada 'RESTAURAR PRODUCAO'.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import backup  # noqa: E402

logger = logging.getLogger("restaurar")
CONFIRMACAO = "RESTAURAR PRODUCAO"


def mesmo_banco(a: str, b: str) -> bool:
    """Mesmo host, porta e banco (a senha e o driver não importam)."""
    ea, eb = backup.ambiente_libpq(a), backup.ambiente_libpq(b)
    return all(ea.get(k) == eb.get(k) for k in ("PGHOST", "PGPORT", "PGDATABASE"))


def exigir_autorizacao(destino_url: str, producao: str | None, permitir: bool, ler=input) -> None:
    if producao and mesmo_banco(destino_url, producao):
        if not permitir:
            raise backup.ErroBackup(
                "O destino é o banco de PRODUÇÃO. Recusado (use outro banco, ou "
                "--permitir-producao com a confirmação)."
            )
        resposta = ler(f"Isto vai escrever no banco de PRODUÇÃO. Digite '{CONFIRMACAO}': ")
        if resposta.strip() != CONFIRMACAO:
            raise backup.ErroBackup("Confirmação incorreta. Nada foi feito.")


def banco_vazio(destino_url: str) -> bool:
    env = {**os.environ, **backup.ambiente_libpq(destino_url)}
    saida = subprocess.run(
        [
            "psql",
            "-X",
            "-A",
            "-t",
            "-c",
            "SELECT count(*) FROM pg_tables"
            " WHERE schemaname NOT IN ('pg_catalog', 'information_schema')",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    if saida.returncode != 0:
        raise backup.ErroBackup(
            "Não foi possível consultar o banco de destino: "
            + backup._resumo(saida.stderr.encode())
        )
    return saida.stdout.strip() == "0"


def escolher(destino: backup.Destino, arquivo: str) -> str:
    nomes = destino.listar()
    if arquivo != "ultimo":
        if arquivo not in nomes:
            raise backup.ErroBackup("Backup não encontrado no destino.")
        return arquivo
    sucesso = [n for n in nomes if backup.data_do_nome(n) and n + backup.SUFIXO_MANIFESTO in nomes]
    if not sucesso:
        raise backup.ErroBackup("Nenhum backup bem-sucedido no destino.")
    return max(sucesso, key=backup.data_do_nome)


def baixar_e_conferir(destino: backup.Destino, nome: str, pasta: Path) -> Path:
    local = pasta / nome
    manifesto = pasta / (nome + backup.SUFIXO_MANIFESTO)
    destino.baixar(nome + backup.SUFIXO_MANIFESTO, manifesto)
    destino.baixar(nome, local)
    esperado = json.loads(manifesto.read_text(encoding="utf-8"))
    sha, tamanho = backup.sha256_arquivo(local)
    if sha != esperado.get("sha256") or tamanho != esperado.get("tamanho_bytes"):
        raise backup.ErroBackup(
            "SHA-256 ou tamanho não confere com o manifesto: arquivo corrompido. Nada foi "
            "decriptado nem restaurado."
        )
    return local


def restaurar(local: Path, identidade: str, destino_url: str) -> None:
    env = {**os.environ, **backup.ambiente_libpq(destino_url)}
    with (
        subprocess.Popen(
            ["age", "-d", "-i", identidade, str(local)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ) as decripta,
        subprocess.Popen(
            ["pg_restore", "--no-owner", "--no-acl", "--exit-on-error", "-d", env["PGDATABASE"]],
            stdin=decripta.stdout,
            stderr=subprocess.PIPE,
            env=env,
        ) as restaura,
    ):
        decripta.stdout.close()
        erro_restaura = restaura.communicate()[1]
        erro_decripta = decripta.stderr.read()
        decripta.wait()
    if decripta.returncode != 0:
        raise backup.ErroBackup(f"age -d falhou: {backup._resumo(erro_decripta)}")
    if restaura.returncode != 0:
        raise backup.ErroBackup(f"pg_restore falhou: {backup._resumo(erro_restaura)}")


def executar(args, destino: backup.Destino | None = None, ler=input) -> str:
    producao = args.url_producao or os.environ.get("OS_DATABASE_URL")
    exigir_autorizacao(args.destino_url, producao, args.permitir_producao, ler)
    if not Path(args.identidade).is_file():
        raise backup.ErroBackup("Arquivo da chave privada (--identidade) não encontrado.")
    if not banco_vazio(args.destino_url):
        raise backup.ErroBackup("O banco de destino não está vazio. Use um banco novo.")
    destino = destino or backup.destino_configurado()
    nome = escolher(destino, args.arquivo)
    with tempfile.TemporaryDirectory(prefix="os-restaurar-") as pasta:
        local = baixar_e_conferir(destino, nome, Path(pasta))
        logger.info("Backup %s: SHA-256 conferido. Restaurando...", nome)
        restaurar(local, args.identidade, args.destino_url)
    logger.info("Backup %s restaurado.", nome)
    return nome


def criar_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Restaura um backup do Sistema de OS.")
    p.add_argument("--arquivo", required=True, help="nome do backup, ou 'ultimo'")
    p.add_argument("--identidade", required=True, help="arquivo da chave PRIVADA do age")
    p.add_argument("--destino-url", required=True, help="URL do banco VAZIO de destino")
    p.add_argument("--url-producao", help="URL de produção (padrão: OS_DATABASE_URL)")
    p.add_argument("--permitir-producao", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        executar(criar_parser().parse_args(argv))
        return 0
    except backup.ErroBackup as exc:
        logger.error("Restauração FALHOU: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
