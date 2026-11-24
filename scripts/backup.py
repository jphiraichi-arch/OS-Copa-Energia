#!/usr/bin/env python3
"""Backup diário criptografado do banco do Sistema de OS (prompt 36). Ver docs/BACKUP.md.

    python scripts/backup.py

Passos (qualquer falha: código de saída diferente de zero, log e, se houver, alerta):
1. ``pg_dump -Fc`` do banco de OS_DATABASE_URL, com a saída ligada direto ao ``age``
   (criptografia com a chave PÚBLICA OS_BACKUP_CHAVE_PUBLICA): o dump sem criptografia
   nunca encosta no disco e nunca fica inteiro na memória.
2. SHA-256 do arquivo criptografado e um manifesto JSON (nome, tamanho, SHA-256, início e
   fim, versões) ao lado.
3. Envio ao destino (OS_BACKUP_DESTINO): 's3' (armazenamento compatível com S3 de outro
   provedor) ou 'pasta' (uma pasta, por exemplo um compartilhamento do servidor da
   empresa montado na máquina).
4. Retenção: apaga backups com mais de OS_BACKUP_RETENCAO_DIAS (padrão 30), nunca o mais
   recente bem-sucedido (o que tem manifesto).
5. Apaga os arquivos temporários locais, com sucesso ou com falha.

Nenhum segredo (URL, chaves de acesso) vai para o log nem para a linha de comando dos
processos: a senha do banco vai para o pg_dump pelo ambiente (PGPASSWORD).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

logger = logging.getLogger("backup")

PREFIXO = "os-"
SUFIXO = ".dump.age"
SUFIXO_MANIFESTO = ".manifest.json"
RE_NOME = re.compile(r"^os-(\d{8}T\d{6}Z)\.dump\.age$")
FORMATO_DATA = "%Y%m%dT%H%M%SZ"
RETENCAO_PADRAO = 30
BLOCO = 1024 * 1024


class ErroBackup(RuntimeError):
    """Falha com mensagem sem segredo."""


# --- Configuração (só deste script; o app não usa estas variáveis) ----------------------


def _var(nome: str, obrigatoria: bool = True, padrao: str | None = None) -> str | None:
    valor = os.environ.get(nome, "").strip()
    if not valor:
        if obrigatoria:
            raise ErroBackup(f"Variável de ambiente obrigatória ausente: {nome}.")
        return padrao
    return valor


def ambiente_libpq(url: str) -> dict[str, str]:
    """URL do PostgreSQL -> variáveis PG* do libpq (a senha não aparece em ``ps``)."""
    url = re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql://", url)
    partes = urlsplit(url)
    if partes.scheme != "postgresql" or not partes.hostname:
        raise ErroBackup("OS_DATABASE_URL não é uma URL de PostgreSQL.")
    env = {
        "PGHOST": partes.hostname,
        "PGPORT": str(partes.port or 5432),
        "PGDATABASE": unquote(partes.path.lstrip("/")),
    }
    if partes.username:
        env["PGUSER"] = unquote(partes.username)
    if partes.password:
        env["PGPASSWORD"] = unquote(partes.password)
    for chave, valores in parse_qs(partes.query).items():
        if chave == "sslmode":
            env["PGSSLMODE"] = valores[-1]
        elif chave == "options":
            env["PGOPTIONS"] = valores[-1]
    return env


# --- Destinos -------------------------------------------------------------------------------


class Destino:
    def enviar(self, local: Path, nome: str) -> None: ...
    def baixar(self, nome: str, local: Path) -> None: ...
    def listar(self) -> list[str]: ...
    def apagar(self, nome: str) -> None: ...


class DestinoPasta(Destino):
    """Uma pasta (por exemplo um compartilhamento do servidor da empresa)."""

    def __init__(self, pasta: str) -> None:
        self.pasta = Path(pasta)
        if not self.pasta.is_dir():
            raise ErroBackup("A pasta de destino do backup não existe.")

    def enviar(self, local: Path, nome: str) -> None:
        temporario = self.pasta / (nome + ".parcial")
        shutil.copyfile(local, temporario)  # copia em blocos
        os.replace(temporario, self.pasta / nome)  # aparece inteiro ou não aparece

    def baixar(self, nome: str, local: Path) -> None:
        shutil.copyfile(self.pasta / nome, local)

    def listar(self) -> list[str]:
        return sorted(p.name for p in self.pasta.iterdir() if p.is_file())

    def apagar(self, nome: str) -> None:
        (self.pasta / nome).unlink(missing_ok=True)


class DestinoS3(Destino):
    """Armazenamento compatível com S3 de OUTRO provedor (boto3, instalado à parte:
    pip install '.[backup]')."""

    def __init__(self, bucket: str) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise ErroBackup(
                "Destino 's3' precisa do pacote boto3: pip install '.[backup]'."
            ) from exc
        self.bucket = bucket
        self.prefixo = _var("OS_BACKUP_S3_PREFIXO", obrigatoria=False, padrao="") or ""
        self.cliente = boto3.client(
            "s3",
            endpoint_url=_var("OS_BACKUP_S3_ENDPOINT", obrigatoria=False),
            region_name=_var("OS_BACKUP_S3_REGIAO", obrigatoria=False),
            aws_access_key_id=_var("OS_BACKUP_S3_CHAVE_ID"),
            aws_secret_access_key=_var("OS_BACKUP_S3_CHAVE_SECRETA"),
        )

    def _chave(self, nome: str) -> str:
        return f"{self.prefixo.rstrip('/')}/{nome}" if self.prefixo else nome

    def enviar(self, local: Path, nome: str) -> None:
        self.cliente.upload_file(str(local), self.bucket, self._chave(nome))  # em partes

    def baixar(self, nome: str, local: Path) -> None:
        self.cliente.download_file(self.bucket, self._chave(nome), str(local))

    def listar(self) -> list[str]:
        nomes: list[str] = []
        paginas = self.cliente.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix=self._chave(PREFIXO)
        )
        for pagina in paginas:
            nomes += [o["Key"].rsplit("/", 1)[-1] for o in pagina.get("Contents", [])]
        return sorted(nomes)

    def apagar(self, nome: str) -> None:
        self.cliente.delete_object(Bucket=self.bucket, Key=self._chave(nome))


def destino_configurado() -> Destino:
    tipo = _var("OS_BACKUP_DESTINO")
    bucket = _var("OS_BACKUP_BUCKET")
    if tipo == "pasta":
        return DestinoPasta(bucket)
    if tipo == "s3":
        return DestinoS3(bucket)
    raise ErroBackup("OS_BACKUP_DESTINO deve ser 's3' ou 'pasta'.")


# --- Funções puras ----------------------------------------------------------------------------


def nome_do_backup(instante: datetime) -> str:
    return f"{PREFIXO}{instante.astimezone(UTC).strftime(FORMATO_DATA)}{SUFIXO}"


def data_do_nome(nome: str) -> datetime | None:
    m = RE_NOME.match(nome)
    return datetime.strptime(m.group(1), FORMATO_DATA).replace(tzinfo=UTC) if m else None


def a_apagar(nomes: Iterable[str], agora: datetime, dias: int) -> list[str]:
    """Backups (e seus manifestos) mais velhos que ``dias``. O mais recente bem-sucedido
    (com manifesto) nunca entra, mesmo se for velho."""
    nomes = set(nomes)
    backups = sorted((n for n in nomes if data_do_nome(n)), key=data_do_nome)
    sucesso = [n for n in backups if n + SUFIXO_MANIFESTO in nomes]
    protegido = sucesso[-1] if sucesso else None
    limite = agora - timedelta(days=dias)
    saida: list[str] = []
    for nome in backups:
        if nome != protegido and data_do_nome(nome) < limite:
            saida.append(nome)
            if nome + SUFIXO_MANIFESTO in nomes:
                saida.append(nome + SUFIXO_MANIFESTO)
    return saida


def sha256_arquivo(caminho: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    tamanho = 0
    with caminho.open("rb") as f:
        while bloco := f.read(BLOCO):
            h.update(bloco)
            tamanho += len(bloco)
    return h.hexdigest(), tamanho


def _versao(comando: str) -> str:
    try:
        saida = subprocess.run([comando, "--version"], capture_output=True, text=True, check=True)
        return saida.stdout.strip().splitlines()[0]
    except (OSError, subprocess.CalledProcessError):
        raise ErroBackup(f"Comando '{comando}' não encontrado.") from None


# --- Backup -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Resultado:
    nome: str
    tamanho: int
    sha256: str
    apagados: tuple[str, ...]


def dump_criptografado(url: str, chave_publica: str, saida: Path) -> None:
    """pg_dump -Fc | age -r CHAVE -o saida. Nada sem criptografia no disco."""
    env = {**os.environ, **ambiente_libpq(url)}
    with (
        subprocess.Popen(
            ["pg_dump", "-Fc", "--no-owner", "--no-acl"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        ) as dump,
        subprocess.Popen(
            ["age", "-r", chave_publica, "-o", str(saida)],
            stdin=dump.stdout,
            stderr=subprocess.PIPE,
        ) as cripto,
    ):
        dump.stdout.close()  # o age é o único leitor
        erro_cripto = cripto.communicate()[1]
        erro_dump = dump.stderr.read()
        dump.wait()
    if dump.returncode != 0:
        raise ErroBackup(f"pg_dump falhou (código {dump.returncode}): {_resumo(erro_dump)}")
    if cripto.returncode != 0:
        raise ErroBackup(f"age falhou (código {cripto.returncode}): {_resumo(erro_cripto)}")


def _resumo(stderr: bytes | None) -> str:
    """Primeira linha do erro, sem a URL (que pode ter senha)."""
    texto = (stderr or b"").decode("utf-8", "replace").strip().splitlines()
    linha = texto[0] if texto else "sem detalhe"
    return re.sub(r"postgres\S*://\S+", "<url>", linha)[:300]


def executar(destino: Destino | None = None, agora: datetime | None = None) -> Resultado:
    url = _var("OS_DATABASE_URL")
    chave = _var("OS_BACKUP_CHAVE_PUBLICA")
    if not chave.startswith("age1"):
        raise ErroBackup("OS_BACKUP_CHAVE_PUBLICA deve ser uma chave pública do age (age1...).")
    dias = int(_var("OS_BACKUP_RETENCAO_DIAS", obrigatoria=False, padrao=str(RETENCAO_PADRAO)))
    destino = destino or destino_configurado()
    inicio = agora or datetime.now(UTC)
    nome = nome_do_backup(inicio)
    versoes = {"pg_dump": _versao("pg_dump"), "age": _versao("age")}
    with tempfile.TemporaryDirectory(prefix="os-backup-") as pasta:
        local = Path(pasta) / nome
        logger.info("Backup %s: iniciando.", nome)
        dump_criptografado(url, chave, local)
        sha, tamanho = sha256_arquivo(local)
        if tamanho == 0:
            raise ErroBackup("O arquivo do backup ficou vazio.")
        fim = datetime.now(UTC)
        manifesto = Path(pasta) / (nome + SUFIXO_MANIFESTO)
        manifesto.write_text(
            json.dumps(
                {
                    "arquivo": nome,
                    "tamanho_bytes": tamanho,
                    "sha256": sha,
                    "inicio": inicio.isoformat(),
                    "fim": fim.isoformat(),
                    "versoes": versoes,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        destino.enviar(local, nome)
        destino.enviar(manifesto, nome + SUFIXO_MANIFESTO)  # o manifesto marca o sucesso
    apagados = a_apagar(destino.listar(), inicio, dias)
    for velho in apagados:
        destino.apagar(velho)
    logger.info(
        "Backup %s: concluído (%s bytes, sha256 %s). Retenção apagou %s arquivo(s).",
        nome,
        tamanho,
        sha,
        len(apagados),
    )
    return Resultado(nome, tamanho, sha, tuple(apagados))


def alertar_falha(etapa: str) -> None:
    """Se o app estiver configurado (alertas do prompt 33), põe um alerta de erro grave
    na fila. Nunca levanta."""
    try:
        from osapp.services import alertas

        alertas.registrar(
            alertas.Ocorrencia(
                f"BackupFalhou:scripts/backup.py:{etapa}"[:200],
                "ERROR",
                "backup",
                datetime.now(UTC),
            )
        )
    except Exception:  # noqa: BLE001 - sem app configurado, fica só o log
        logger.warning("Alerta de falha do backup não registrado (app indisponível).")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        executar()
        return 0
    except ErroBackup as exc:
        logger.error("Backup FALHOU: %s", exc)
        alertar_falha("erro")
        return 1
    except Exception as exc:  # noqa: BLE001
        logger.error("Backup FALHOU: erro inesperado (%s).", type(exc).__name__)
        alertar_falha(type(exc).__name__)
        return 2


if __name__ == "__main__":
    sys.exit(main())
