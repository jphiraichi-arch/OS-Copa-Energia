"""Cadastro de filiais e usuários para o seed e a CLI (executados pelo operador do servidor).

Não há ator: estas funções não são expostas pela interface web.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import select

from osapp.db import sessao
from osapp.models import CategoriaCusto, Filial, OrdemServico, Usuario
from osapp.models.ordem_servico import INCLUIR_EXCLUIDAS
from osapp.repositories import (
    CategoriaCustoRepo,
    FilialRepo,
    UsuarioRepo,
)
from osapp.services import ordens as ordens_servico
from osapp.services import protecao_login, relogio, sla, usuarios
from osapp.services.auth import LOGIN_MAX
from osapp.services.auth import PAPEIS as PAPEIS_DO_ATOR
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
    e_admin: bool
    is_gerente: bool = False
    papel: str = "manutencao"


PERFIS = ("usuario", "gerente", "administrador")
PAPEIS = PAPEIS_DO_ATOR


def papel_de(e_admin: bool) -> str:
    """Papel a partir do perfil antigo (regra da migração 0007)."""
    return "admin" if e_admin else "manutencao"


@dataclass(frozen=True)
class PreviaPapel:
    login: str
    filial_codigo: str
    e_admin: bool
    papel_proposto: str


def _texto(campo: str, valor: object, minimo: int, maximo: int) -> str:
    if not isinstance(valor, str):
        raise ErroValidacao(campo, "Valor inválido.")
    valor = valor.strip()
    if not minimo <= len(valor) <= maximo:
        raise ErroValidacao(campo, f"Deve ter de {minimo} a {maximo} caracteres.")
    return valor


def validar_senha(senha: object, login: str | None = None) -> str:
    """A mesma regra da gestão de usuários: pelo menos 10 caracteres e diferente do login."""
    return usuarios.validar_senha_nova(senha, login)


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
        sla.criar_padroes(s, filial.id)  # prompt 38: a filial nova recebe os alvos padrão
        logger.info("Filial criada: id=%s.", filial.id)
        return FilialCriada(filial.id, filial.codigo, filial.nome)


def criar_usuario(
    nome: str,
    login: str,
    senha: str,
    filial_codigo: str,
    e_admin: bool = False,
    is_gerente: bool = False,
    *,
    papel: str | None = None,
    temporaria: bool = False,
) -> UsuarioCriado:
    """Cria um usuário pela linha de comando ou pelo seed (sem administrador logado).

    ``papel`` (usuario, manutencao, admin); sem ele, ``e_admin`` decide entre admin e
    manutencao. ``temporaria``: o usuário troca a senha no próximo login. As regras e o
    histórico são os de services/usuarios.py.
    """
    if not isinstance(e_admin, bool):
        raise ErroValidacao("e_admin", "Valor inválido.")
    if papel is None:
        papel = papel_de(e_admin)
    if papel not in PAPEIS or (e_admin and papel != "admin"):
        raise ErroValidacao("papel", "Papel inválido. Use usuario, manutencao ou admin.")
    if not isinstance(filial_codigo, str):
        raise ErroValidacao("filial", "Filial inválida.")
    with sessao() as s:
        filial = FilialRepo(s).obter_por_codigo(filial_codigo.strip().upper())
        if filial is None:
            raise ErroValidacao("filial", "Filial não encontrada.")
        usuario = usuarios.criar(
            s, None, nome, login, filial.id, papel, senha, is_gerente, temporaria
        )
        return UsuarioCriado(
            usuario.id,
            usuario.nome,
            usuario.login,
            filial.codigo,
            papel == "admin",
            usuario.is_gerente,
            papel,
        )


def _usuario_por_login(s, login: object) -> Usuario:
    usuario = UsuarioRepo(s).obter_por_login(login.strip()) if isinstance(login, str) else None
    if usuario is None:
        raise ErroNaoEncontrado()
    return usuario


def redefinir_senha(login: str, senha: str, temporaria: bool = True) -> None:
    """Senha nova (temporária por padrão) e zera o atraso progressivo daquele login."""
    with sessao() as s:
        usuarios.redefinir(s, None, _usuario_por_login(s, login), senha, temporaria)


def limpar_tentativas_antigas() -> int:
    """Apaga contadores de login expirados (uso manual; o app também limpa sozinho)."""
    apagadas = protecao_login.apagar_expiradas(relogio.agora())
    logger.info("Tentativas de login expiradas apagadas: %s.", apagadas)
    return apagadas


def desativar_usuario(login: str) -> None:
    with sessao() as s:
        usuarios.alterar(s, None, _usuario_por_login(s, login), {"ativo": False})


def definir_perfil(login: str, perfil: str) -> None:
    """Muda o perfil de um usuário: 'usuario', 'gerente' ou 'administrador'."""
    if perfil not in PERFIS:
        raise ErroValidacao("perfil", "Perfil inválido. Use usuario, gerente ou administrador.")
    with sessao() as s:
        usuario = _usuario_por_login(s, login)
        alteracoes: dict = {"gerente": perfil == "gerente"}
        if perfil == "administrador":
            alteracoes["papel"] = "admin"
        elif usuario.papel == "admin":
            alteracoes["papel"] = "manutencao"
        usuarios.alterar(s, None, usuario, alteracoes)


def previa_papeis() -> list[PreviaPapel]:
    """Login, filial, e_admin (derivado) e o papel atual. Não altera nada.

    Desde a migração 0008 não há mais coluna e_admin: a prévia antes da 0007 deve ser
    feita com o código do prompt 16 (commit 3c66de8).
    """
    with sessao() as s:
        linhas = s.execute(
            select(Usuario.login, Filial.codigo, Usuario.papel)
            .join(Filial, Usuario.filial_id == Filial.id)
            .order_by(Filial.codigo, Usuario.login)
        ).all()
    return [PreviaPapel(login, codigo, papel == "admin", papel) for login, codigo, papel in linhas]


def definir_papel(login: str, papel: str) -> None:
    """Corrige o papel de um usuário: 'usuario', 'manutencao' ou 'admin'."""
    if papel not in PAPEIS:
        raise ErroValidacao("papel", "Papel inválido. Use usuario, manutencao ou admin.")
    with sessao() as s:
        usuarios.alterar(s, None, _usuario_por_login(s, login), {"papel": papel})


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


# --- Texto de busca ---------------------------------------------------------------


def recalcular_busca() -> dict[str, int]:
    """Refaz busca_texto de todas as ordens e itens. Idempotente: num banco coerente não
    muda nada. Devolve quantas ordens e itens mudaram."""
    from osapp.busca import normalizar_busca
    from osapp.models import OsItemCusto

    mudou = {"ordens": 0, "itens": 0}
    with sessao() as s:
        # Inclui as ordens da lixeira: ao restaurar, a busca já está certa.
        for ordem in s.scalars(select(OrdemServico).execution_options(**{INCLUIR_EXCLUIDAS: True})):
            certo = normalizar_busca(f"{ordem.titulo or ''} {ordem.descricao or ''}")
            if ordem.busca_texto != certo:
                ordem.busca_texto = certo
                mudou["ordens"] += 1
        for item in s.scalars(select(OsItemCusto)):
            certo = normalizar_busca(item.descricao)
            if item.busca_texto != certo:
                item.busca_texto = certo
                mudou["itens"] += 1
    logger.info("Busca recalculada: %s.", mudou)
    return mudou


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
    # Inclui as ordens da lixeira: nenhuma ordem pode ficar numa filial consolidada.
    ordens = list(
        s.scalars(
            select(OrdemServico)
            .where(OrdemServico.filial_id != destino.id)
            .execution_options(**{INCLUIR_EXCLUIDAS: True})
        )
    )
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
        if not (responsavel.papel == "admin" and responsavel.ativo):
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


# --- Campos de evento sem rótulo (prompt 26) -------------------------------------------


def campos_de_eventos() -> list[str]:
    """Valores distintos de os_eventos.campo (só leitura; sem os vazios)."""
    from osapp.models import OsEvento

    with sessao() as s:
        consulta = select(OsEvento.campo).where(OsEvento.campo.is_not(None)).distinct()
        return sorted(s.scalars(consulta))


# --- Conferência do histórico de status (prompt 25) ----------------------------------

TOLERANCIA_SEGUNDOS = 60  # coluna e evento gravados na mesma transação, com o mesmo relógio


@dataclass(frozen=True)
class Divergencia:
    numero: str
    problema: str


def verificar_eventos_status() -> list[Divergencia]:
    """Só leitura. Para cada ordem (lixeira incluída), refaz a linha do tempo pelos
    eventos CRIACAO e STATUS e compara com o status atual e as colunas de instante."""
    from datetime import datetime as _dt

    from osapp.models import OsEvento
    from osapp.services import linha_do_tempo
    from osapp.services import status as _status

    def longe(a, b) -> bool:
        if a is None or b is None:
            return (a is None) != (b is None)
        return abs((a - b).total_seconds()) > TOLERANCIA_SEGUNDOS

    achados: list[Divergencia] = []
    with sessao() as s:
        eventos: dict[int, list] = {}
        consulta = (
            select(
                OsEvento.os_id,
                OsEvento.data_hora,
                OsEvento.tipo,
                OsEvento.valor_antigo,
                OsEvento.valor_novo,
            )
            .where(OsEvento.tipo.in_(("CRIACAO", "STATUS")))
            .order_by(OsEvento.os_id, OsEvento.data_hora, OsEvento.id)
        )
        for os_id, data_hora, tipo, antigo, novo in s.execute(consulta):
            eventos.setdefault(os_id, []).append((data_hora, tipo, antigo, novo))
        ordens = s.scalars(
            select(OrdemServico)
            .order_by(OrdemServico.id)
            .execution_options(**{INCLUIR_EXCLUIDAS: True})
        )
        futuro = _dt.max.replace(tzinfo=relogio.agora().tzinfo)
        for o in ordens:
            lista = eventos.get(o.id, [])
            marcos = [linha_do_tempo.Marco(d, t, n) for d, t, _a, n in lista]
            if not any(t == "CRIACAO" for _d, t, _a, _n in lista):
                achados.append(Divergencia(o.numero, "sem evento CRIACAO"))
            anterior = _status.ABERTA
            for _d, tipo, antigo, novo in lista:
                if tipo == "STATUS":
                    if antigo != anterior:
                        achados.append(
                            Divergencia(o.numero, f"transição de {antigo} depois de {anterior}")
                        )
                    anterior = novo
            sit = linha_do_tempo.situacao_em(marcos, futuro)
            if sit.status != o.status:
                achados.append(
                    Divergencia(o.numero, f"status {o.status}; pelos eventos {sit.status}")
                )
            criacao = next((d for d, t, _a, _n in lista if t == "CRIACAO"), None)
            for nome, coluna, evento in (
                ("aberta_em", o.aberta_em, criacao),
                ("inicio_execucao_em", o.inicio_execucao_em, sit.inicio),
                ("concluida_em", o.concluida_em, sit.concluida_em),
                ("cancelada_em", o.cancelada_em, sit.cancelada_em),
            ):
                if longe(coluna, evento):
                    achados.append(
                        Divergencia(o.numero, f"{nome} {coluna} difere do evento {evento}")
                    )
    return achados
