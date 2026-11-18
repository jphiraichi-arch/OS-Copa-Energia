"""Proteção do login: atraso progressivo por login e por IP, no lugar do bloqueio fixo.

- Por login: as 3 primeiras falhas não custam nada; a partir da 4ª, a próxima tentativa
  daquele login só é aceita depois de 2, 4, 8, 16... segundos (no máximo 15 minutos).
  Um login bem-sucedido zera a contagem. Logins inexistentes contam do mesmo jeito.
- Por IP: mais de OS_LIMITE_FALHAS_IP falhas (padrão 100) do mesmo IP em 15 minutos põem
  o IP numa espera progressiva curta (no máximo OS_ATRASO_MAX_IP_SEGUNDOS, padrão 60 s),
  para qualquer login. Nunca bloqueia: celulares em 4G dividem IP (CGNAT).
- Contadores expirados (IP: 15 min sem falha; login: 30 dias sem atividade) não contam e
  são apagados ao registrar uma nova tentativa da mesma chave e numa varredura ao iniciar.
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
from osapp.db import sessao
from osapp.models.tentativa_login import TIPO_IP, TIPO_LOGIN, TentativaLogin
from osapp.repositories import TentativaLoginRepo

VARIAVEL_SEGREDO = "OS_HMAC_SEGREDO"
SEGREDO_MIN = 32  # caracteres

FALHAS_LIVRES_LOGIN = 3
ATRASO_MAXIMO = timedelta(minutes=15)  # teto por login (a proteção principal)
DIAS_DE_RETENCAO = 30  # contador de login sem atividade expira depois disso

# Por IP: operadoras de celular usam CGNAT (muita gente atrás do mesmo IP). O limite é
# bem mais alto que o do login e o teto da espera é curto: o IP nunca fica bloqueado.
VARIAVEL_FALHAS_IP = "OS_LIMITE_FALHAS_IP"
VARIAVEL_ATRASO_IP = "OS_ATRASO_MAX_IP_SEGUNDOS"
FALHAS_LIVRES_IP_PADRAO = 100
ATRASO_MAX_IP_PADRAO = 60  # segundos
JANELA_IP = timedelta(minutes=15)  # contador de IP sem falha há mais que isso expira
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


# --- Limites por IP (configuráveis) ----------------------------------------------------


def _inteiro_positivo(nome: str, padrao: int) -> int:
    load_dotenv()
    bruto = os.environ.get(nome, "").strip()
    if not bruto:
        return padrao
    try:
        valor = int(bruto)
    except ValueError:
        raise ConfigError(f"{nome} inválida: {bruto!r} não é um número inteiro.") from None
    if valor <= 0:
        raise ConfigError(f"{nome} inválida: deve ser maior que zero.")
    return valor


def falhas_livres_ip() -> int:
    """Falhas de um IP (na janela de 15 min) antes de começar a espera. Padrão 100."""
    return _inteiro_positivo(VARIAVEL_FALHAS_IP, FALHAS_LIVRES_IP_PADRAO)


def atraso_maximo_ip() -> timedelta:
    """Teto da espera por IP. Padrão 60 s."""
    return timedelta(seconds=_inteiro_positivo(VARIAVEL_ATRASO_IP, ATRASO_MAX_IP_PADRAO))


def validar_configuracao() -> None:
    """Chamada ao iniciar o app: segredo e limites válidos, senão ConfigError."""
    segredo()
    falhas_livres_ip()
    atraso_maximo_ip()


# --- Regras (puras) --------------------------------------------------------------------


def atraso(falhas: int, livres: int, teto: timedelta = ATRASO_MAXIMO) -> timedelta:
    """Espera depois da falha número ``falhas``: zero até ``livres``; depois 2, 4, 8... s."""
    excedentes = falhas - livres
    if excedentes <= 0:
        return timedelta(0)
    if excedentes >= 20:  # 2**20 s já passa muito de qualquer teto; evita números enormes
        return teto
    return min(timedelta(seconds=2**excedentes), teto)


def bloqueada(tentativa: TentativaLogin, agora: datetime) -> bool:
    """True se ainda não chegou o instante da próxima tentativa permitida."""
    return tentativa.proximo_permitido_em is not None and agora < tentativa.proximo_permitido_em


def validade(tipo: str) -> timedelta:
    """Tempo sem atividade depois do qual um contador expira (e deixa de contar)."""
    return JANELA_IP if tipo == TIPO_IP else timedelta(days=DIAS_DE_RETENCAO)


def registrar_falha(tentativa: TentativaLogin, agora: datetime) -> None:
    """Conta uma falha e calcula o próximo instante permitido."""
    if tentativa.tipo == TIPO_IP:
        livres, teto = falhas_livres_ip(), atraso_maximo_ip()
    else:
        livres, teto = FALHAS_LIVRES_LOGIN, ATRASO_MAXIMO
    tentativa.falhas += 1
    espera = atraso(tentativa.falhas, livres, teto)
    tentativa.proximo_permitido_em = agora + espera if espera else None
    tentativa.atualizado_em = agora


def registrar_sucesso(tentativa: TentativaLogin, agora: datetime) -> None:
    """Login certo: zera a contagem daquele login (a do IP continua)."""
    tentativa.falhas = 0
    tentativa.proximo_permitido_em = None
    tentativa.atualizado_em = agora


# --- Banco -----------------------------------------------------------------------------


def travar_contador(s, tipo: str, chave_: str, agora: datetime) -> TentativaLogin:
    """Contador da chave, travado na transação. Antes, apaga o da chave se expirou:
    contadores expirados nunca entram na contagem."""
    repo = TentativaLoginRepo(s)
    repo.apagar_expiradas(agora, {tipo: agora - validade(tipo)}, chave=chave_)
    return repo.travar(tipo, chave_, agora)


def apagar_expiradas(agora: datetime) -> int:
    """Apaga todos os contadores expirados (limpeza ao iniciar e comando manual)."""
    limites = {tipo: agora - validade(tipo) for tipo in (TIPO_LOGIN, TIPO_IP)}
    with sessao() as s:
        return TentativaLoginRepo(s).apagar_expiradas(agora, limites)


def limpeza_ao_iniciar() -> None:
    """Varredura leve ao subir o servidor. Uma falha aqui não impede o app de iniciar."""
    from osapp.services import relogio

    try:
        apagadas = apagar_expiradas(relogio.agora())
        logger.info("Contadores de login expirados apagados ao iniciar: %s.", apagadas)
    except Exception:  # noqa: BLE001 - a limpeza é oportunista
        logger.warning("Limpeza de contadores de login ao iniciar falhou.", exc_info=True)


__all__ = [
    "ATRASO_MAXIMO",
    "DIAS_DE_RETENCAO",
    "FALHAS_LIVRES_IP_PADRAO",
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
    "apagar_expiradas",
    "atraso_maximo_ip",
    "falhas_livres_ip",
    "limpeza_ao_iniciar",
    "registrar_falha",
    "registrar_sucesso",
    "segredo",
    "travar_contador",
    "validade",
    "validar_configuracao",
]
