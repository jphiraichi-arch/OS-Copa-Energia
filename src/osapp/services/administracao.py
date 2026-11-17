"""Cadastro de filiais e usuários para o seed e a CLI (executados pelo operador do servidor).

Não há ator: estas funções não são expostas pela interface web.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from osapp.db import sessao
from osapp.models import Filial, Usuario
from osapp.repositories import FilialRepo, UsuarioRepo
from osapp.services import senhas
from osapp.services.auth import LOGIN_MAX
from osapp.services.erros import ErroConflito, ErroNaoEncontrado, ErroValidacao

logger = logging.getLogger(__name__)

_RE_CODIGO = re.compile(r"^[A-Z0-9]{1,10}$")
_RE_LOGIN = re.compile(rf"^[a-z0-9._-]{{3,{LOGIN_MAX}}}$")


@dataclass(frozen=True)
class FilialCriada:
    id: int
    codigo: str
    nome: str


@dataclass(frozen=True)
class UsuarioCriado:
    id: int
    nome: str
    login: str
    filial_codigo: str
    is_admin: bool
    is_gerente: bool = False


PERFIS = ("usuario", "gerente", "administrador")


def _texto(campo: str, valor: object, minimo: int, maximo: int) -> str:
    if not isinstance(valor, str):
        raise ErroValidacao(campo, "Valor inválido.")
    valor = valor.strip()
    if not minimo <= len(valor) <= maximo:
        raise ErroValidacao(campo, f"Deve ter de {minimo} a {maximo} caracteres.")
    return valor


def validar_senha(senha: object) -> str:
    if not isinstance(senha, str) or not senhas.SENHA_MIN <= len(senha) <= senhas.SENHA_MAX:
        raise ErroValidacao(
            "senha", f"A senha deve ter de {senhas.SENHA_MIN} a {senhas.SENHA_MAX} caracteres."
        )
    return senha


def _validar_login(login: object) -> str:
    if not isinstance(login, str) or not _RE_LOGIN.match(login.strip().lower()):
        raise ErroValidacao(
            "login",
            f"O login deve ter de 3 a {LOGIN_MAX} caracteres: letras, números, ponto, "
            "hífen ou sublinhado.",
        )
    return login.strip().lower()


def criar_filial(codigo: str, nome: str) -> FilialCriada:
    if not isinstance(codigo, str) or not _RE_CODIGO.match(codigo.strip().upper()):
        raise ErroValidacao("codigo", "O código deve ter de 1 a 10 letras ou números.")
    codigo = codigo.strip().upper()
    nome = _texto("nome", nome, 1, 100)
    with sessao() as s:
        repo = FilialRepo(s)
        if repo.obter_por_codigo(codigo) is not None:
            raise ErroConflito()
        filial = repo.adicionar(Filial(codigo=codigo, nome=nome))
        logger.info("Filial criada: id=%s.", filial.id)
        return FilialCriada(filial.id, filial.codigo, filial.nome)


def criar_usuario(
    nome: str,
    login: str,
    senha: str,
    filial_codigo: str,
    is_admin: bool = False,
    is_gerente: bool = False,
) -> UsuarioCriado:
    nome = _texto("nome", nome, 1, 100)
    login = _validar_login(login)
    validar_senha(senha)
    if not isinstance(is_admin, bool):
        raise ErroValidacao("is_admin", "Valor inválido.")
    if not isinstance(is_gerente, bool) or (is_admin and is_gerente):
        raise ErroValidacao("perfil", "Escolha um único perfil: usuário, gerente ou administrador.")
    if not isinstance(filial_codigo, str):
        raise ErroValidacao("filial", "Filial inválida.")
    with sessao() as s:
        filial = FilialRepo(s).obter_por_codigo(filial_codigo.strip().upper())
        if filial is None:
            raise ErroValidacao("filial", "Filial não encontrada.")
        repo = UsuarioRepo(s)
        if repo.obter_por_login(login) is not None:
            raise ErroConflito()
        usuario = repo.adicionar(
            Usuario(
                nome=nome,
                login=login,
                senha_hash=senhas.gerar_hash(senha),
                filial_id=filial.id,
                is_admin=is_admin,
                is_gerente=is_gerente,
            )
        )
        logger.info("Usuário criado: usuario_id=%s.", usuario.id)
        return UsuarioCriado(
            usuario.id, usuario.nome, usuario.login, filial.codigo, is_admin, is_gerente
        )


def _usuario_por_login(s, login: object) -> Usuario:
    usuario = UsuarioRepo(s).obter_por_login(login.strip()) if isinstance(login, str) else None
    if usuario is None:
        raise ErroNaoEncontrado()
    return usuario


def redefinir_senha(login: str, senha: str) -> None:
    """Troca a senha e remove bloqueio e contagem de falhas."""
    validar_senha(senha)
    with sessao() as s:
        usuario = _usuario_por_login(s, login)
        usuario.senha_hash = senhas.gerar_hash(senha)
        usuario.tentativas_falhas = 0
        usuario.bloqueado_ate = None
        logger.info("Senha redefinida: usuario_id=%s.", usuario.id)


def desativar_usuario(login: str) -> None:
    with sessao() as s:
        usuario = _usuario_por_login(s, login)
        usuario.ativo = False
        logger.info("Usuário desativado: usuario_id=%s.", usuario.id)


def definir_perfil(login: str, perfil: str) -> None:
    """Muda o perfil de um usuário: 'usuario', 'gerente' ou 'administrador'."""
    if perfil not in PERFIS:
        raise ErroValidacao("perfil", "Perfil inválido. Use usuario, gerente ou administrador.")
    with sessao() as s:
        usuario = _usuario_por_login(s, login)
        usuario.is_admin = perfil == "administrador"
        usuario.is_gerente = perfil == "gerente"
        logger.info("Perfil alterado: usuario_id=%s perfil=%s.", usuario.id, perfil)
