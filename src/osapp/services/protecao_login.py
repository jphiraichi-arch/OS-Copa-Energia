"""Proteção do login: atraso progressivo por login e por IP, no lugar do bloqueio fixo.

- Por login: as 3 primeiras falhas não custam nada; a partir da 4ª, a próxima tentativa
  daquele login só é aceita depois de 2, 4, 8, 16... segundos (no máximo 15 minutos).
  Um login bem-sucedido zera a contagem. Logins inexistentes contam do mesmo jeito.
- Por IP: mais de 20 falhas do mesmo IP em 15 minutos põem o IP na mesma regra, para
  qualquer login.
- O servidor nunca dorme: grava o instante da próxima tentativa permitida e recusa até lá.
- As chaves são HMAC-SHA256 com o segredo OS_HMAC_SEGREDO: o banco e os logs nunca têm o
  IP nem o login digitado.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

from osapp.config import ConfigError
from osapp.models.tentativa_login import TIPO_IP, TIPO_LOGIN, TentativaLogin

VARIAVEL_SEGREDO = "OS_HMAC_SEGREDO"
SEGREDO_MIN = 32  # caracteres

FALHAS_LIVRES_LOGIN = 3
FALHAS_LIVRES_IP = 20
JANELA_IP = timedelta(minutes=15)
ATRASO_MAXIMO = timedelta(minutes=15)
DIAS_DE_RETENCAO = 30
IP_DESCONHECIDO = "desconhecido"

MENSAGEM_MUITAS_TENTATIVAS = "Muitas tentativas. Aguarde alguns instantes e tente novamente."

logger = logging.getLogger(__name__)


# --- Segredo e chaves ------------------------------------------------------------------


def segredo() -> bytes:
    """O segredo do HMAC. Ausente ou curto levanta ConfigError (o app não deve iniciar)."""
    load_dotenv()
    valor = os.environ.get(VARIAVEL_SEGREDO, "")
    if len(valor) < SEGREDO_MIN:
        raise ConfigError(
            f"Variável de ambiente obrigatória ausente ou curta: {VARIAVEL_SEGREDO} "
            f"(mínimo de {SEGREDO_MIN} caracteres aleatórios)."
        )
    return valor.encode("utf-8")


def chave(valor: str) -> str:
    """HMAC-SHA256 (64 caracteres hexadecimais) do login normalizado ou do IP."""
    return hmac.new(segredo(), valor.encode("utf-8"), hashlib.sha256).hexdigest()


def chave_do_login(login: str) -> str:
    return chave("login:" + login.strip().lower())


def chave_do_ip(ip: str | None) -> str:
    """Chave do IP. Sem IP conhecido usa a chave fixa 'desconhecido' e registra um aviso."""
    if not ip:
        logger.warning("IP do cliente desconhecido: usado o limite comum 'desconhecido'.")
        ip = IP_DESCONHECIDO
    return chave("ip:" + ip.strip().lower())


# --- Regras (puras) --------------------------------------------------------------------


def atraso(falhas: int, livres: int) -> timedelta:
    """Espera depois da falha número ``falhas``: zero até ``livres``; depois 2, 4, 8... s."""
    excedentes = falhas - livres
    if excedentes <= 0:
        return timedelta(0)
    if excedentes >= 20:  # 2**20 s já passa muito do teto; evita números enormes
        return ATRASO_MAXIMO
    return min(timedelta(seconds=2**excedentes), ATRASO_MAXIMO)


def bloqueada(tentativa: TentativaLogin, agora: datetime) -> bool:
    """True se ainda não chegou o instante da próxima tentativa permitida."""
    return tentativa.proximo_permitido_em is not None and agora < tentativa.proximo_permitido_em


def registrar_falha(tentativa: TentativaLogin, agora: datetime) -> None:
    """Conta uma falha e calcula o próximo instante permitido.

    Para IP, a contagem recomeça quando a última falha tem mais de 15 minutos.
    """
    if tentativa.tipo == TIPO_IP:
        livres = FALHAS_LIVRES_IP
        if tentativa.falhas and agora - tentativa.atualizado_em > JANELA_IP:
            tentativa.falhas = 0
    else:
        livres = FALHAS_LIVRES_LOGIN
    tentativa.falhas += 1
    espera = atraso(tentativa.falhas, livres)
    tentativa.proximo_permitido_em = agora + espera if espera else None
    tentativa.atualizado_em = agora


def registrar_sucesso(tentativa: TentativaLogin, agora: datetime) -> None:
    """Login certo: zera a contagem daquele login (a do IP continua)."""
    tentativa.falhas = 0
    tentativa.proximo_permitido_em = None
    tentativa.atualizado_em = agora


__all__ = [
    "ATRASO_MAXIMO",
    "DIAS_DE_RETENCAO",
    "FALHAS_LIVRES_IP",
    "FALHAS_LIVRES_LOGIN",
    "IP_DESCONHECIDO",
    "JANELA_IP",
    "MENSAGEM_MUITAS_TENTATIVAS",
    "TIPO_IP",
    "TIPO_LOGIN",
    "atraso",
    "bloqueada",
    "chave",
    "chave_do_ip",
    "chave_do_login",
    "registrar_falha",
    "registrar_sucesso",
    "segredo",
]
