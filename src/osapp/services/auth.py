"""Autenticação e identidade do ator.

Nunca registra em log senha, hash, IP ou o texto digitado no campo de login: os logs
trazem só o id do usuário e as chaves HMAC (services/protecao_login.py).
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass

from osapp.db import sessao
from osapp.models import Usuario
from osapp.models.tentativa_login import TIPO_IP, TIPO_LOGIN
from osapp.repositories import UsuarioRepo
from osapp.services import protecao_login, relogio, senhas
from osapp.services.erros import ErroAutenticacao, ErroMuitasTentativas

LOGIN_MAX = 50

PAPEL_USUARIO = "usuario"
PAPEL_MANUTENCAO = "manutencao"
PAPEL_ADMIN = "admin"
PAPEIS = (PAPEL_USUARIO, PAPEL_MANUTENCAO, PAPEL_ADMIN)

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
    papel: str  # 'usuario', 'manutencao' ou 'admin'
    is_gerente: bool = False
    deve_trocar_senha: bool = False  # senha temporária: trocar antes de qualquer tela
    # Prompt 34: filiais permitidas (inclui a padrão, ``filial_id``). O administrador
    # acessa todas de qualquer forma (permissoes.pode_acessar_filial).
    filiais_permitidas: tuple[int, ...] = ()

    @property
    def filiais(self) -> tuple[int, ...]:
        return self.filiais_permitidas or (self.filial_id,)

    @property
    def e_admin(self) -> bool:
        """Atalho de leitura: o papel é 'admin'."""
        return self.papel == PAPEL_ADMIN

    @property
    def e_manutencao(self) -> bool:
        return self.papel == PAPEL_MANUTENCAO

    @property
    def e_usuario(self) -> bool:
        return self.papel == PAPEL_USUARIO


def _ator_de(usuario: Usuario) -> Ator:
    return Ator(
        usuario_id=usuario.id,
        nome=usuario.nome,
        filial_id=usuario.filial_id,
        filial_codigo=usuario.filial.codigo,
        papel=usuario.papel,
        is_gerente=usuario.is_gerente and usuario.papel != PAPEL_ADMIN,
        deve_trocar_senha=usuario.deve_trocar_senha,
        filiais_permitidas=usuario.filiais_ids,
    )


def autenticar(login: str, senha: str, ip: str | None = None) -> Ator:
    """Confere login e senha. Qualquer falha levanta o mesmo ErroAutenticacao.

    ``ip`` é o IP do cliente (Page.client_ip). Antes do instante permitido para o login
    ou para o IP a tentativa é recusada com ErroMuitasTentativas, sem conferir a senha.
    Logins inexistentes e inativos contam falhas como os demais.
    """
    if not isinstance(login, str) or not isinstance(senha, str):
        logger.warning("Falha de autenticação: entrada inválida.")
        raise ErroAutenticacao()
    login = login.strip().lower()
    if not login or not senha or len(login) > LOGIN_MAX or len(senha) > senhas.SENHA_MAX:
        logger.warning("Falha de autenticação: entrada vazia ou acima do tamanho permitido.")
        raise ErroAutenticacao()

    chave_login = protecao_login.chave_do_login(login)
    chave_ip = protecao_login.chave_do_ip(ip)
    ator: Ator | None = None
    recusada = False
    # Os contadores precisam ser confirmados mesmo quando o login falha; por isso o erro
    # só é levantado depois de a sessão fechar com commit.
    with sessao() as s:
        agora = relogio.agora()
        # Sempre na mesma ordem (login, depois IP), para duas transações não se travarem.
        por_login = protecao_login.travar_contador(s, TIPO_LOGIN, chave_login, agora)
        por_ip = protecao_login.travar_contador(s, TIPO_IP, chave_ip, agora)
        if protecao_login.bloqueada(por_login, agora) or protecao_login.bloqueada(por_ip, agora):
            recusada = True
            logger.warning(
                "Tentativa recusada antes do instante permitido: login=%s ip=%s.",
                chave_login,
                chave_ip,
            )
        else:
            usuario = UsuarioRepo(s).obter_por_login(login)
            if usuario is None:
                senhas.verificar(senha, _HASH_FICTICIO)
                confere = False
            else:
                confere = senhas.verificar(senha, usuario.senha_hash) and usuario.ativo
            if confere:
                protecao_login.registrar_sucesso(por_login, agora)
                if senhas.precisa_rehash(usuario.senha_hash):
                    usuario.senha_hash = senhas.gerar_hash(senha)
                ator = _ator_de(usuario)
                logger.info(
                    "Login bem-sucedido: usuario_id=%s login=%s ip=%s.",
                    usuario.id,
                    chave_login,
                    chave_ip,
                )
            else:
                protecao_login.registrar_falha(por_login, agora)
                protecao_login.registrar_falha(por_ip, agora)
                logger.warning(
                    "Falha de autenticação: login=%s (falha %s) ip=%s (falha %s).",
                    chave_login,
                    por_login.falhas,
                    chave_ip,
                    por_ip.falhas,
                )
    if recusada:
        raise ErroMuitasTentativas()
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
