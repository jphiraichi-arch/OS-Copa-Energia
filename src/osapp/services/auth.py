"""Autenticação e identidade do ator.

Nunca registra em log senha, hash ou o texto digitado no campo de login.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta

from osapp.db import sessao
from osapp.models import Usuario
from osapp.repositories import UsuarioRepo
from osapp.services import relogio, senhas
from osapp.services.erros import ErroAutenticacao

LOGIN_MAX = 50
MAX_TENTATIVAS = 5
MINUTOS_DE_BLOQUEIO = 15

logger = logging.getLogger(__name__)

# Hash usado quando o login não existe, para que o tempo de resposta não revele
# quais logins existem. A senha correspondente é aleatória e descartada.
_HASH_FICTICIO = senhas.gerar_hash(secrets.token_urlsafe(32))


@dataclass(frozen=True)
class Ator:
    """Quem está agindo. Recarregado do banco a cada chamada de serviço."""

    usuario_id: int
    nome: str
    filial_id: int
    filial_codigo: str
    is_admin: bool


def _ator_de(usuario: Usuario) -> Ator:
    return Ator(
        usuario_id=usuario.id,
        nome=usuario.nome,
        filial_id=usuario.filial_id,
        filial_codigo=usuario.filial.codigo,
        is_admin=usuario.is_admin,
    )


def autenticar(login: str, senha: str) -> Ator:
    """Confere login e senha. Qualquer falha levanta o mesmo ErroAutenticacao."""
    if not isinstance(login, str) or not isinstance(senha, str):
        logger.warning("Falha de autenticação: entrada inválida.")
        raise ErroAutenticacao()
    login = login.strip().lower()
    if not login or not senha or len(login) > LOGIN_MAX or len(senha) > senhas.SENHA_MAX:
        logger.warning("Falha de autenticação: entrada vazia ou acima do tamanho permitido.")
        raise ErroAutenticacao()

    ator: Ator | None = None
    # As alterações de contadores precisam ser confirmadas mesmo quando o login falha;
    # por isso o erro só é levantado depois de a sessão fechar com commit.
    with sessao() as s:
        usuario = UsuarioRepo(s).obter_por_login(login)
        agora = relogio.agora()
        if usuario is None:
            senhas.verificar(senha, _HASH_FICTICIO)
            logger.warning("Falha de autenticação: login inexistente.")
        else:
            confere = senhas.verificar(senha, usuario.senha_hash)
            if not usuario.ativo:
                logger.warning("Falha de autenticação: usuario_id=%s inativo.", usuario.id)
            elif usuario.bloqueado_ate is not None and agora < usuario.bloqueado_ate:
                logger.warning("Falha de autenticação: usuario_id=%s bloqueado.", usuario.id)
            else:
                if usuario.bloqueado_ate is not None:  # bloqueio vencido: nova contagem
                    usuario.bloqueado_ate = None
                    usuario.tentativas_falhas = 0
                    s.flush()
                if confere:
                    usuario.tentativas_falhas = 0
                    if senhas.precisa_rehash(usuario.senha_hash):
                        usuario.senha_hash = senhas.gerar_hash(senha)
                    ator = _ator_de(usuario)
                    logger.info("Login bem-sucedido: usuario_id=%s.", usuario.id)
                else:
                    # Incremento feito no banco, para não perder tentativas simultâneas.
                    usuario.tentativas_falhas = Usuario.tentativas_falhas + 1
                    s.flush()
                    s.refresh(usuario)
                    if usuario.tentativas_falhas >= MAX_TENTATIVAS:
                        usuario.bloqueado_ate = agora + timedelta(minutes=MINUTOS_DE_BLOQUEIO)
                        logger.warning(
                            "Falha de autenticação: usuario_id=%s bloqueado por %s minutos "
                            "após %s tentativas.",
                            usuario.id,
                            MINUTOS_DE_BLOQUEIO,
                            usuario.tentativas_falhas,
                        )
                    else:
                        logger.warning(
                            "Falha de autenticação: usuario_id=%s senha incorreta (tentativa %s).",
                            usuario.id,
                            usuario.tentativas_falhas,
                        )
    if ator is None:
        raise ErroAutenticacao()
    return ator


def carregar_ator(usuario_id: int) -> Ator:
    """Recarrega o usuário do banco. Ausente ou inativo levanta ErroAutenticacao.

    Toda função de serviço começa por aqui: desativar um usuário vale imediatamente.
    """
    if isinstance(usuario_id, bool) or not isinstance(usuario_id, int):
        raise ErroAutenticacao()
    with sessao() as s:
        usuario = UsuarioRepo(s).obter(usuario_id)
        if usuario is None or not usuario.ativo:
            logger.warning("Ator recusado: usuario_id=%s ausente ou inativo.", usuario_id)
            raise ErroAutenticacao()
        return _ator_de(usuario)
