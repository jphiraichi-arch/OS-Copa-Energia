"""Configuração da aplicação, lida exclusivamente de variáveis de ambiente."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

TZ_PADRAO = "America/Sao_Paulo"
SESSAO_TIMEOUT_MIN_PADRAO = 30
LOG_LEVEL_PADRAO = "INFO"
NIVEIS_DE_LOG = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def normalizar_url_do_banco(url: str) -> str:
    """Faz URLs 'postgres://' e 'postgresql://' usarem o driver psycopg (versão 3).

    Serviços de nuvem entregam a URL nesses formatos; o SQLAlchemy precisa do driver
    no esquema. As demais URLs ficam como estão.
    """
    for prefixo in ("postgres://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url[len(prefixo) :]
    return url


class ConfigError(RuntimeError):
    """Configuração ausente ou inválida. A aplicação não deve iniciar."""


@dataclass(frozen=True)
class Config:
    database_url: str
    tz: str
    sessao_timeout_min: int
    log_level: str

    def __repr__(self) -> str:  # a URL do banco pode conter senha: nunca exibir
        return (
            f"Config(database_url='***', tz={self.tz!r}, "
            f"sessao_timeout_min={self.sessao_timeout_min!r}, log_level={self.log_level!r})"
        )


def carregar_config(env: Mapping[str, str] | None = None) -> Config:
    """Lê e valida a configuração.

    Sem argumento, carrega um eventual arquivo .env local (desenvolvimento) e lê
    os.environ. Com ``env`` explícito, usa somente o mapeamento recebido.
    Levanta ConfigError com mensagem clara se algo estiver ausente ou inválido.
    """
    if env is None:
        load_dotenv()
        env = os.environ

    database_url = env.get("OS_DATABASE_URL", "").strip()
    if not database_url:
        raise ConfigError(
            "Variável de ambiente obrigatória ausente: OS_DATABASE_URL. "
            "Defina-a no ambiente ou em um arquivo .env (veja .env.example)."
        )

    tz = env.get("OS_TZ", "").strip() or TZ_PADRAO
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"OS_TZ inválida: {tz!r} não é um fuso horário IANA.") from exc

    bruto = env.get("OS_SESSAO_TIMEOUT_MIN", "").strip() or str(SESSAO_TIMEOUT_MIN_PADRAO)
    try:
        sessao_timeout_min = int(bruto)
    except ValueError as exc:
        raise ConfigError(
            f"OS_SESSAO_TIMEOUT_MIN inválida: {bruto!r} não é um número inteiro."
        ) from exc
    if sessao_timeout_min <= 0:
        raise ConfigError("OS_SESSAO_TIMEOUT_MIN inválida: deve ser maior que zero.")

    log_level = (env.get("OS_LOG_LEVEL", "").strip() or LOG_LEVEL_PADRAO).upper()
    if log_level not in NIVEIS_DE_LOG:
        raise ConfigError(
            f"OS_LOG_LEVEL inválida: {log_level!r}. Use um de: {', '.join(NIVEIS_DE_LOG)}."
        )

    return Config(
        database_url=normalizar_url_do_banco(database_url),
        tz=tz,
        sessao_timeout_min=sessao_timeout_min,
        log_level=log_level,
    )
