"""Configuração da aplicação, lida exclusivamente de variáveis de ambiente.

Este é o ÚNICO módulo que lê o ambiente (há teste). A lista completa, com padrões e
significado, está em docs/CONFIGURACAO.md e em .env.example. Nada aqui depende de um
provedor de hospedagem ou de banco: valores próprios de um provedor ficam só nas
configurações da hospedagem.

- ``carregar_config()``: o essencial, validado na partida (banco, fuso, sessão, log,
  conexão com o banco).
- Funções pequenas (``fuso()``, ``segredo_hmac()``, ``smtp()``...): leem um grupo de
  variáveis sob demanda, para que mudanças no ambiente (e nos testes) valham na hora.
"""

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
RECICLAR_CONEXAO_PADRAO = 300  # segundos
TIMEOUT_CONEXAO_PADRAO = 10  # segundos

# Nomes das variáveis (todas documentadas em docs/CONFIGURACAO.md).
VAR_DATABASE_URL = "OS_DATABASE_URL"
VAR_TZ = "OS_TZ"
VAR_SESSAO_TIMEOUT = "OS_SESSAO_TIMEOUT_MIN"
VAR_LOG_LEVEL = "OS_LOG_LEVEL"
VAR_RECICLAR_CONEXAO = "OS_DB_RECICLAR_CONEXAO_SEGUNDOS"
VAR_TIMEOUT_CONEXAO = "OS_DB_TIMEOUT_CONEXAO_SEGUNDOS"
VAR_HMAC = "OS_HMAC_SEGREDO"
VAR_FALHAS_IP = "OS_LIMITE_FALHAS_IP"
VAR_ATRASO_IP = "OS_ATRASO_MAX_IP_SEGUNDOS"
VAR_PROXIES = "OS_PROXIES_CONFIAVEIS"
VAR_CABECALHO_IP = "OS_CABECALHO_IP_CLIENTE"
VAR_DEPURAR_IP = "OS_DEPURAR_CABECALHOS_IP"
VAR_SEED_SENHA = "OS_SEED_SENHA"
VAR_SEED_EXEMPLOS = "OS_SEED_EXEMPLOS"
VAR_SMTP_HOST = "OS_SMTP_HOST"
VAR_SMTP_PORTA = "OS_SMTP_PORTA"
VAR_SMTP_USUARIO = "OS_SMTP_USUARIO"
VAR_SMTP_SENHA = "OS_SMTP_SENHA"
VAR_SMTP_REMETENTE = "OS_SMTP_REMETENTE"
VAR_SMTP_TLS = "OS_SMTP_TLS"
VAR_BASE_URL = "OS_BASE_URL"
VAR_EMAIL_MAX_TENTATIVAS = "OS_EMAIL_MAX_TENTATIVAS"
VAR_ALERTAS = "OS_ALERTAS_EMAIL"
VAR_EMAIL_HABILITADO = "OS_EMAIL_HABILITADO"
VAR_GUIA = "OS_GUIA_ARQUIVO"
VAR_AMBIENTE = "OS_AMBIENTE"
GUIA_PADRAO = "docs/guia/guia.yaml"

# Prompt 42: visualizações de administradores não contam como 'Visualizada' (constante
# de configuração do sistema, não variável de ambiente).
CONTAR_VISUALIZACAO_ADMIN = False

_dotenv_lido = False


def _ambiente() -> Mapping[str, str]:
    """os.environ, depois de ler uma vez um eventual .env local (desenvolvimento).
    O .env nunca sobrescreve uma variável já definida no ambiente."""
    global _dotenv_lido
    if not _dotenv_lido:
        load_dotenv()
        _dotenv_lido = True
    return os.environ


def _texto(nome: str, env: Mapping[str, str] | None = None) -> str:
    return (env if env is not None else _ambiente()).get(nome, "").strip()


def normalizar_url_do_banco(url: str) -> str:
    """Faz URLs 'postgres://' e 'postgresql://' usarem o driver psycopg (versão 3).

    É a forma padrão de URL do PostgreSQL; o SQLAlchemy precisa do driver no esquema.
    As demais URLs ficam como estão.
    """
    for prefixo in ("postgres://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url[len(prefixo) :]
    return url


class ConfigError(RuntimeError):
    """Configuração ausente ou inválida. A aplicação não deve iniciar."""


def inteiro_positivo(nome: str, padrao: int, env: Mapping[str, str] | None = None) -> int:
    bruto = _texto(nome, env)
    if not bruto:
        return padrao
    try:
        valor = int(bruto)
    except ValueError:
        raise ConfigError(f"{nome} inválida: {bruto!r} não é um número inteiro.") from None
    if valor <= 0:
        raise ConfigError(f"{nome} inválida: deve ser maior que zero.")
    return valor


@dataclass(frozen=True)
class Config:
    database_url: str
    tz: str
    sessao_timeout_min: int
    log_level: str
    db_reciclar_conexao_s: int = RECICLAR_CONEXAO_PADRAO
    db_timeout_conexao_s: int = TIMEOUT_CONEXAO_PADRAO

    def __repr__(self) -> str:  # a URL do banco pode conter senha: nunca exibir
        return (
            f"Config(database_url='***', tz={self.tz!r}, "
            f"sessao_timeout_min={self.sessao_timeout_min!r}, log_level={self.log_level!r})"
        )


def carregar_config(env: Mapping[str, str] | None = None) -> Config:
    """Lê e valida a configuração essencial.

    Sem argumento, carrega um eventual arquivo .env local (desenvolvimento) e lê
    os.environ. Com ``env`` explícito, usa somente o mapeamento recebido.
    Levanta ConfigError com mensagem clara se algo estiver ausente ou inválido.
    Não existe URL de banco padrão.
    """
    if env is None:
        load_dotenv()
        env = os.environ

    database_url = _texto(VAR_DATABASE_URL, env)
    if not database_url:
        raise ConfigError(
            f"Variável de ambiente obrigatória ausente: {VAR_DATABASE_URL}. "
            "Defina-a no ambiente ou em um arquivo .env (veja .env.example)."
        )

    tz = _texto(VAR_TZ, env) or TZ_PADRAO
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"{VAR_TZ} inválida: {tz!r} não é um fuso horário IANA.") from exc

    bruto = _texto(VAR_SESSAO_TIMEOUT, env) or str(SESSAO_TIMEOUT_MIN_PADRAO)
    try:
        sessao_timeout_min = int(bruto)
    except ValueError as exc:
        raise ConfigError(
            f"{VAR_SESSAO_TIMEOUT} inválida: {bruto!r} não é um número inteiro."
        ) from exc
    if sessao_timeout_min <= 0:
        raise ConfigError(f"{VAR_SESSAO_TIMEOUT} inválida: deve ser maior que zero.")

    log_level = (_texto(VAR_LOG_LEVEL, env) or LOG_LEVEL_PADRAO).upper()
    if log_level not in NIVEIS_DE_LOG:
        raise ConfigError(
            f"{VAR_LOG_LEVEL} inválida: {log_level!r}. Use um de: {', '.join(NIVEIS_DE_LOG)}."
        )

    return Config(
        database_url=normalizar_url_do_banco(database_url),
        tz=tz,
        sessao_timeout_min=sessao_timeout_min,
        log_level=log_level,
        db_reciclar_conexao_s=inteiro_positivo(VAR_RECICLAR_CONEXAO, RECICLAR_CONEXAO_PADRAO, env),
        db_timeout_conexao_s=inteiro_positivo(VAR_TIMEOUT_CONEXAO, TIMEOUT_CONEXAO_PADRAO, env),
    )


# --- Leituras sob demanda ---------------------------------------------------------------


def fuso() -> str:
    """Fuso de exibição (OS_TZ, padrão America/Sao_Paulo). Validado em carregar_config."""
    return _texto(VAR_TZ) or TZ_PADRAO


def segredo_hmac() -> str:
    """OS_HMAC_SEGREDO cru (o tamanho mínimo é conferido em services/protecao_login)."""
    return _ambiente().get(VAR_HMAC, "")


def limite_falhas_ip(padrao: int) -> int:
    return inteiro_positivo(VAR_FALHAS_IP, padrao)


def atraso_max_ip_segundos(padrao: int) -> int:
    return inteiro_positivo(VAR_ATRASO_IP, padrao)


def proxies_confiaveis() -> str | None:
    return _texto(VAR_PROXIES) or None


def cabecalho_ip_cliente() -> str | None:
    """Nome de um cabeçalho que o proxy confiável preenche com o IP do cliente (ex.:
    'True-Client-Ip'). Vazio (padrão): só o X-Forwarded-For é usado."""
    return _texto(VAR_CABECALHO_IP).lower() or None


def depurar_cabecalhos_ip() -> bool:
    return _texto(VAR_DEPURAR_IP) == "1"


def seed_senha() -> str:
    return _ambiente().get(VAR_SEED_SENHA, "")


def seed_exemplos() -> bool:
    return _texto(VAR_SEED_EXEMPLOS) == "1"


@dataclass(frozen=True)
class SmtpBruto:
    """Valores crus do SMTP; a validação fica em services/fila_email.py."""

    host: str
    porta: str
    usuario: str | None
    senha: str | None
    remetente: str
    tls: str

    def __repr__(self) -> str:  # a senha nunca aparece
        return f"SmtpBruto(host={self.host!r}, porta={self.porta!r}, tls={self.tls!r})"


def smtp() -> SmtpBruto:
    env = _ambiente()
    return SmtpBruto(
        host=_texto(VAR_SMTP_HOST),
        porta=_texto(VAR_SMTP_PORTA),
        usuario=_texto(VAR_SMTP_USUARIO) or None,
        senha=env.get(VAR_SMTP_SENHA) or None,
        remetente=_texto(VAR_SMTP_REMETENTE),
        tls=_texto(VAR_SMTP_TLS).lower(),
    )


def base_url() -> str | None:
    return _texto(VAR_BASE_URL) or None


def email_max_tentativas(padrao: int) -> int:
    texto = _texto(VAR_EMAIL_MAX_TENTATIVAS)
    if texto.isdigit() and int(texto) > 0:
        return int(texto)
    return padrao


def email_habilitado() -> bool:
    """OS_EMAIL_HABILITADO (prompt 46): '1' liga o e-mail. Padrão: desligado. Desligado, o
    trabalhador da fila não sobe e nada entra em email_fila (avisos, códigos, alertas):
    sem isso as linhas se acumulariam e sairiam todas atrasadas quando o e-mail voltasse.
    Os erros graves continuam no log do servidor."""
    return _texto(VAR_EMAIL_HABILITADO) == "1"


def alertas_por_email() -> bool:
    """OS_ALERTAS_EMAIL: '0' desliga o e-mail dos alertas de erro grave (só log).
    Padrão: ligado."""
    return _texto(VAR_ALERTAS) != "0"


def guia_arquivo() -> str:
    """OS_GUIA_ARQUIVO: caminho do guia rápido (prompt 39). Padrão: docs/guia/guia.yaml,
    relativo à pasta em que o app roda."""
    return _texto(VAR_GUIA) or GUIA_PADRAO


def ambiente() -> str:
    """OS_AMBIENTE: 'producao', 'homologacao', 'desenvolvimento'... (prompt 41: o comando
    preparar-piloto recusa 'producao' sem um segundo aviso). Padrão: vazio."""
    return _texto(VAR_AMBIENTE).lower()


def nome_do_banco(url: str) -> str:
    """O nome do banco na URL (para a confirmação digitada do preparar-piloto)."""
    from urllib.parse import urlsplit

    if url.startswith("sqlite"):
        return url.rsplit("/", 1)[-1] or "memoria"
    return urlsplit(normalizar_url_do_banco(url).replace("+psycopg", "")).path.lstrip("/")
