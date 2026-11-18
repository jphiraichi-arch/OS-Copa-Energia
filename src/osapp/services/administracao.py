"""Cadastro de filiais e usuários para o seed e a CLI (executados pelo operador do servidor).

Não há ator: estas funções não são expostas pela interface web.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select

from osapp.db import sessao
from osapp.models import CategoriaCusto, Equipamento, Filial, OrdemServico, Usuario
from osapp.models.tentativa_login import TIPO_LOGIN
from osapp.repositories import (
    CategoriaCustoRepo,
    EquipamentoRepo,
    FilialRepo,
    TentativaLoginRepo,
    UsuarioRepo,
)
from osapp.services import ordens as ordens_servico
from osapp.services import protecao_login, relogio, senhas
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
    """Troca a senha e zera o atraso progressivo daquele login."""
    validar_senha(senha)
    with sessao() as s:
        usuario = _usuario_por_login(s, login)
        usuario.senha_hash = senhas.gerar_hash(senha)
        TentativaLoginRepo(s).apagar(TIPO_LOGIN, protecao_login.chave_do_login(usuario.login))
        logger.info("Senha redefinida: usuario_id=%s.", usuario.id)


def limpar_tentativas_antigas() -> int:
    """Apaga contadores de falha de login sem atividade há mais de 30 dias. Devolve quantos."""
    limite = relogio.agora() - timedelta(days=protecao_login.DIAS_DE_RETENCAO)
    with sessao() as s:
        apagadas = TentativaLoginRepo(s).apagar_anteriores(limite)
    logger.info("Tentativas de login antigas apagadas: %s.", apagadas)
    return apagadas


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


# --- Cadastros básicos (seed) ----------------------------------------------------------

# (código, nome, ordem). A migração 0004 também os cria; aqui só se completa o que faltar.
CATEGORIAS_PADRAO = (
    ("MAO_DE_OBRA", "Mão de obra", 1),
    ("PECAS_MATERIAIS", "Peças/materiais", 2),
    ("SERVICOS_TERCEIROS", "Serviços de terceiros", 3),
    ("OUTROS", "Outros", 4),
)


def garantir_categorias() -> int:
    """Cria as categorias padrão que faltarem. Devolve quantas criou."""
    criadas = 0
    with sessao() as s:
        repo = CategoriaCustoRepo(s)
        for codigo, nome, ordem in CATEGORIAS_PADRAO:
            if repo.obter_por_codigo(codigo) is None:
                repo.adicionar(CategoriaCusto(codigo=codigo, nome=nome, ordem=ordem))
                criadas += 1
    return criadas


def garantir_equipamento(filial_codigo: str, nome: str) -> bool:
    """Cria o equipamento na filial se ainda não existir com esse nome. True se criou."""
    nome = _texto("nome", nome, 1, 120)
    with sessao() as s:
        filial = FilialRepo(s).obter_por_codigo(filial_codigo)
        if filial is None:
            raise ErroValidacao("filial", "Filial não encontrada.")
        repo = EquipamentoRepo(s)
        if repo.obter_por_nome(filial.id, nome) is not None:
            return False
        repo.adicionar(Equipamento(filial_id=filial.id, nome=nome))
        return True


# --- Consolidação na filial 1007 -------------------------------------------------------

# Logins fictícios criados pelos seeds anteriores: são desativados, nunca apagados.
LOGINS_FICTICIOS = ("marina.teste", "joao.ficticio", "carlos.exemplo", "gerente.norte")


@dataclass(frozen=True)
class PlanoConsolidacao:
    filial_destino: str
    filiais_de_origem: tuple[str, ...]  # "código - nome: N usuário(s), M OS"
    desativar_usuarios: tuple[str, ...]  # logins
    mover_usuarios: tuple[str, ...]  # logins
    mover_ordens: tuple[str, ...]  # números das OS

    @property
    def vazio(self) -> bool:
        return not (self.desativar_usuarios or self.mover_usuarios or self.mover_ordens)


def _plano(s, destino: Filial) -> tuple[PlanoConsolidacao, list[Usuario], list[Usuario], list]:
    usuarios = list(s.scalars(select(Usuario).order_by(Usuario.id)))
    ordens = list(s.scalars(select(OrdemServico).where(OrdemServico.filial_id != destino.id)))
    desativar = [u for u in usuarios if u.login in LOGINS_FICTICIOS and u.ativo]
    mover = [u for u in usuarios if u.login not in LOGINS_FICTICIOS and u.filial_id != destino.id]
    origens = []
    for filial in FilialRepo(s).listar():
        if filial.id == destino.id:
            continue
        n_u = sum(1 for u in usuarios if u.filial_id == filial.id)
        n_o = sum(1 for o in ordens if o.filial_id == filial.id)
        origens.append(f"{filial.codigo} - {filial.nome}: {n_u} usuário(s), {n_o} OS")
    plano = PlanoConsolidacao(
        filial_destino=f"{destino.codigo} - {destino.nome}",
        filiais_de_origem=tuple(origens),
        desativar_usuarios=tuple(u.login for u in desativar),
        mover_usuarios=tuple(u.login for u in mover),
        mover_ordens=tuple(o.numero for o in ordens),
    )
    return plano, desativar, mover, ordens


def _filial_destino(s, codigo: str) -> Filial:
    destino = FilialRepo(s).obter_por_codigo(codigo)
    if destino is None:
        raise ErroValidacao("filial", "Filial de destino não encontrada. Rode o seed antes.")
    return destino


def planejar_consolidacao(codigo_destino: str = "1007") -> PlanoConsolidacao:
    """Simulação: lista o que seria desativado ou movido. Não altera nada."""
    with sessao() as s:
        plano, *_ = _plano(s, _filial_destino(s, codigo_destino))
        s.rollback()
        return plano


def aplicar_consolidacao(login_responsavel: str, codigo_destino: str = "1007") -> PlanoConsolidacao:
    """Aplica o plano numa só transação. Nada é apagado.

    Usuários fictícios são desativados; os demais e todas as OS de outras filiais passam
    para a filial de destino. Cada OS movida ganha um evento EDICAO de filial, em nome do
    administrador responsável (as filiais de origem ficam vazias, mas não são apagadas).
    """
    with sessao() as s:
        responsavel = _usuario_por_login(s, login_responsavel)
        if not (responsavel.is_admin and responsavel.ativo):
            raise ErroValidacao("responsavel", "O responsável deve ser um administrador ativo.")
        destino = _filial_destino(s, codigo_destino)
        plano, desativar, mover, ordens = _plano(s, destino)
        agora = relogio.agora()
        for usuario in desativar:
            usuario.ativo = False
        for usuario in mover:
            usuario.filial_id = destino.id
        for ordem in ordens:
            ordens_servico.registrar_evento(
                s,
                ordem.id,
                responsavel.id,
                ordens_servico.TIPO_EDICAO,
                agora,
                "filial_id",
                ordem.filial.codigo,
                destino.codigo,
            )
            ordem.filial_id = destino.id
            ordem.atualizado_em = agora
        logger.info(
            "Consolidação aplicada: %s desativado(s), %s usuário(s) e %s OS movidos.",
            len(desativar),
            len(mover),
            len(ordens),
        )
        return plano
