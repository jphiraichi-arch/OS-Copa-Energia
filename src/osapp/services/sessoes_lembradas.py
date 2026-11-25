"""'Lembrar de mim por 7 dias' (prompt 35): tokens com hash, rotação e revogação.

O token fica no armazenamento do navegador (SharedPreferences do Flet). Como qualquer um
com acesso ao navegador pode lê-lo, a proteção é toda do servidor:

- Token: 32 bytes do ``secrets``, URL-safe. O banco guarda só o SHA-256 (um token longo e
  aleatório não precisa de hash lento). Nunca vai para log.
- Vida: ``expira_em`` = login + 7 dias. A rotação NÃO estende: depois de 7 dias a senha
  volta a ser pedida.
- Uso: token válido (não expirado, não revogado, usuário ativo) entra e é trocado por
  outro na mesma família, com o mesmo ``expira_em``; o antigo fica marcado como usado.
- Um token já trocado apresentado de novo foi copiado: a família inteira é revogada,
  a entrada é recusada e um aviso de segurança vai para o log (usuário e família, nunca
  o token).
- Qualquer recusa é igual para quem tenta (ErroAutenticacao) e conta para o limite por
  IP do prompt 15.
- Revogação: 'Sair' (a família do aparelho), 'Sair de todos os aparelhos', troca e
  redefinição de senha, desativação (``revogar_sessoes_lembradas``) e o administrador.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from osapp.db import sessao
from osapp.models import SessaoLembrada
from osapp.models.tentativa_login import TIPO_IP
from osapp.repositories import UsuarioRepo
from osapp.services import protecao_login, relogio
from osapp.services.auth import Ator, _ator_de, carregar_ator
from osapp.services.erros import ErroAutenticacao, ErroMuitasTentativas, ErroNaoEncontrado
from osapp.services.permissoes import exigir_admin

logger = logging.getLogger(__name__)

VALIDADE = timedelta(days=7)
RETENCAO = timedelta(days=30)
TOKEN_BYTES = 32
TOKEN_MAX = 100  # um token_urlsafe(32) tem 43 caracteres
CHAVE_NAVEGADOR = "osapp.lembrar"  # chave no armazenamento do navegador
ROTULO_MAX = 60


# --- Funções puras ---------------------------------------------------------------------------


def gerar_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


_NAVEGADORES = (
    (r"EdgA?/|Edg/", "Edge"),
    (r"SamsungBrowser/", "Samsung Internet"),
    (r"OPR/|Opera", "Opera"),
    (r"Firefox/|FxiOS/", "Firefox"),
    (r"CriOS/|Chrome/", "Chrome"),
    (r"Safari/", "Safari"),
)
_SISTEMAS = (
    (r"iPhone", "iPhone"),
    (r"iPad", "iPad"),
    (r"Android", "Android"),
    (r"Windows", "Windows"),
    (r"Mac OS X|Macintosh", "macOS"),
    (r"CrOS", "ChromeOS"),
    (r"Linux", "Linux"),
)


def rotulo_aparelho(user_agent: str | None) -> str:
    """'Chrome em Android', 'Safari em iPhone'... Nunca o user agent cru."""
    texto = user_agent or ""
    navegador = next((n for p, n in _NAVEGADORES if re.search(p, texto)), "Navegador")
    sistema = next((n for p, n in _SISTEMAS if re.search(p, texto)), None)
    rotulo = f"{navegador} em {sistema}" if sistema else navegador
    return rotulo[:ROTULO_MAX]


# --- Modelos de leitura ---------------------------------------------------------------------


@dataclass(frozen=True)
class Emitido:
    """O token NOVO para o navegador guardar (devolvido uma vez) e a família."""

    token: str
    familia: str

    def __repr__(self) -> str:  # o token nunca aparece em log
        return f"Emitido(familia={self.familia!r}, token='***')"


@dataclass(frozen=True)
class EntradaLembrada:
    ator: Ator
    emitido: Emitido


@dataclass(frozen=True)
class Aparelho:
    familia: str
    rotulo: str
    criado_em: datetime
    ultimo_uso_em: datetime
    expira_em: datetime


# --- Emissão ---------------------------------------------------------------------------------


def _emitir(
    s: Session, usuario_id: int, familia: str, rotulo: str, expira_em: datetime, agora
) -> Emitido:
    token = gerar_token()
    s.add(
        SessaoLembrada(
            usuario_id=usuario_id,
            familia=familia,
            token_hash=hash_token(token),
            criado_em=agora,
            expira_em=expira_em,
            rotulo_aparelho=rotulo,
        )
    )
    s.flush()
    return Emitido(token, familia)


def lembrar(ator_id: int, user_agent: str | None) -> Emitido:
    """Depois de um login com a caixa marcada: nova família, válida por 7 dias."""
    ator = carregar_ator(ator_id, permitir_senha_temporaria=True)
    with sessao() as s:
        agora = relogio.agora()
        emitido = _emitir(
            s,
            ator.usuario_id,
            secrets.token_hex(16),
            rotulo_aparelho(user_agent),
            agora + VALIDADE,
            agora,
        )
    logger.info("Lembrar de mim: família %s criada para usuario_id=%s.", emitido.familia, ator_id)
    return emitido


# --- Uso -------------------------------------------------------------------------------------


def _revogar_familia(s: Session, familia: str, agora: datetime) -> int:
    resultado = s.execute(
        update(SessaoLembrada)
        .where(SessaoLembrada.familia == familia, SessaoLembrada.revogado_em.is_(None))
        .values(revogado_em=agora)
        .execution_options(synchronize_session=False)
    )
    return resultado.rowcount or 0


def entrar_com_token(token: object, ip: str | None = None) -> EntradaLembrada:
    """Entra com o token guardado no navegador. Qualquer recusa: ErroAutenticacao (o
    navegador apaga o token). Recusas contam para o limite por IP; com o IP em espera,
    ErroMuitasTentativas (subclasse de ErroAutenticacao)."""
    chave_ip = protecao_login.chave_do_ip(ip)
    resultado: EntradaLembrada | None = None
    recusa = "token"
    with sessao() as s:
        agora = relogio.agora()
        por_ip = protecao_login.travar_contador(s, TIPO_IP, chave_ip, agora)
        if protecao_login.bloqueada(por_ip, agora):
            recusa = "ip"
        elif isinstance(token, str) and 0 < len(token) <= TOKEN_MAX:
            linha = s.scalars(
                select(SessaoLembrada)
                .where(SessaoLembrada.token_hash == hash_token(token))
                .with_for_update()
            ).one_or_none()
            if linha is not None and linha.revogado_em is None:
                if linha.ultimo_uso_em is not None:
                    _revogar_familia(s, linha.familia, agora)
                    logger.warning(
                        "SEGURANÇA: token 'lembrar de mim' já trocado foi usado de novo; "
                        "família revogada. usuario_id=%s familia=%s.",
                        linha.usuario_id,
                        linha.familia,
                    )
                elif agora < linha.expira_em:
                    usuario = UsuarioRepo(s).obter(linha.usuario_id)
                    if usuario is not None and usuario.ativo:
                        linha.ultimo_uso_em = agora
                        novo = _emitir(
                            s,
                            usuario.id,
                            linha.familia,
                            linha.rotulo_aparelho,
                            linha.expira_em,  # a rotação não estende a validade
                            agora,
                        )
                        resultado = EntradaLembrada(_ator_de(usuario), novo)
        if resultado is None and recusa == "token":
            protecao_login.registrar_falha(por_ip, agora)
    if recusa == "ip":
        logger.warning("Token 'lembrar de mim' recusado: IP em espera (ip=%s).", chave_ip)
        raise ErroMuitasTentativas()
    if resultado is None:
        logger.warning("Token 'lembrar de mim' recusado (ip=%s).", chave_ip)
        raise ErroAutenticacao()
    logger.info(
        "Entrada lembrada: usuario_id=%s familia=%s.",
        resultado.ator.usuario_id,
        resultado.emitido.familia,
    )
    return resultado


# --- Revogação --------------------------------------------------------------------------------


def revogar_sessoes_lembradas(usuario_id: int, s: Session | None = None) -> int:
    """Revoga todos os tokens do usuário (troca e redefinição de senha, desativação).
    Com ``s``, na mesma transação de quem chama. Devolve quantos."""

    def _revogar(sess: Session) -> int:
        r = sess.execute(
            update(SessaoLembrada)
            .where(SessaoLembrada.usuario_id == usuario_id, SessaoLembrada.revogado_em.is_(None))
            .values(revogado_em=relogio.agora())
            .execution_options(synchronize_session=False)
        )
        return r.rowcount or 0

    if s is not None:
        total = _revogar(s)
    else:
        with sessao() as nova:
            total = _revogar(nova)
    if total:
        logger.info("Lembrar de mim: %s token(s) revogado(s) de usuario_id=%s.", total, usuario_id)
    return total


def sair_deste_aparelho(ator_id: int, familia: object) -> None:
    """'Sair' num aparelho, ou 'Sair deste aparelho' na lista: só famílias do próprio."""
    ator = carregar_ator(ator_id, permitir_senha_temporaria=True)
    if not isinstance(familia, str):
        return
    with sessao() as s:
        dono = s.scalar(
            select(SessaoLembrada.usuario_id).where(SessaoLembrada.familia == familia).limit(1)
        )
        if dono != ator.usuario_id:
            raise ErroNaoEncontrado()
        _revogar_familia(s, familia, relogio.agora())


def sair_de_todos(ator_id: int) -> int:
    ator = carregar_ator(ator_id)
    return revogar_sessoes_lembradas(ator.usuario_id)


def revogar_de_usuario(ator_id: int, usuario_id: object) -> int:
    """Administrador: revoga todos os tokens de outro usuário."""
    ator = carregar_ator(ator_id)
    exigir_admin(ator)
    if not isinstance(usuario_id, int) or isinstance(usuario_id, bool):
        raise ErroNaoEncontrado()
    total = revogar_sessoes_lembradas(usuario_id)
    logger.info(
        "Administrador revogou os aparelhos: usuario_id=%s autor_id=%s.", usuario_id, ator_id
    )
    return total


def listar_aparelhos(ator_id: int) -> list[Aparelho]:
    """Aparelhos com token ativo do próprio usuário: rótulo, criado (início da família)
    e último uso (a emissão do token atual)."""
    ator = carregar_ator(ator_id)
    with sessao() as s:
        agora = relogio.agora()
        linhas = list(
            s.scalars(
                select(SessaoLembrada)
                .where(SessaoLembrada.usuario_id == ator.usuario_id)
                .order_by(SessaoLembrada.id)
            )
        )
    inicio: dict[str, datetime] = {}
    for linha in linhas:
        inicio.setdefault(linha.familia, linha.criado_em)
    ativos = [
        linha
        for linha in linhas
        if linha.revogado_em is None and linha.ultimo_uso_em is None and agora < linha.expira_em
    ]
    return [
        Aparelho(
            linha.familia,
            linha.rotulo_aparelho,
            inicio[linha.familia],
            linha.criado_em,
            linha.expira_em,
        )
        for linha in sorted(ativos, key=lambda x: x.criado_em, reverse=True)
    ]


def limpar(agora: datetime | None = None) -> int:
    """Comando de linha: apaga linhas expiradas ou revogadas há mais de 30 dias."""
    agora = agora or relogio.agora()
    limite = agora - RETENCAO
    with sessao() as s:
        r = s.execute(
            delete(SessaoLembrada)
            .where(or_(SessaoLembrada.expira_em < limite, SessaoLembrada.revogado_em < limite))
            .execution_options(synchronize_session=False)
        )
        return r.rowcount or 0
