"""Gestão de usuários (só administrador) e troca da própria senha (todos).

Regras:
- Só um administrador cria, altera (nome, filial, papel, ativo) e redefine a senha de
  usuários, em qualquer filial. Usuários nunca são apagados: são desativados.
- Senha: pelo menos 10 caracteres e diferente do login. Na tela, a senha de um usuário
  novo ou redefinida é GERADA pelo sistema (prompt 34), mostrada uma vez ao
  administrador e temporária: o usuário a troca no próximo login. A linha de comando
  continua pedindo a senha (getpass).
- Filiais permitidas (prompts 28 e 34): um ou mais; a filial padrão é uma delas.
- Precisa existir sempre pelo menos um administrador ativo: o último não perde o papel
  nem se desativa.
- Toda mudança grava uma linha por campo em usuarios_eventos (só inserção). Para senha,
  grava 'senha redefinida' ou 'senha alterada', nunca a senha nem o hash.
- A linha de comando usa as mesmas funções internas, sem administrador (admin_id nulo).
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from osapp.db import sessao
from osapp.models import Filial, Usuario, UsuarioEvento, UsuarioNotificacao
from osapp.models.tentativa_login import TIPO_LOGIN
from osapp.repositories import FilialRepo, TentativaLoginRepo, UsuarioRepo
from osapp.services import protecao_login, relogio, senhas, sessoes_lembradas
from osapp.services.auth import LOGIN_MAX, PAPEIS, carregar_ator
from osapp.services.erros import (
    ErroConflito,
    ErroNaoEncontrado,
    ErroPermissao,
    ErroValidacao,
)
from osapp.services.permissoes import exigir_admin

logger = logging.getLogger(__name__)

NOME_MAX = 100
BUSCA_MAX = 100
CAMPOS_ALTERAVEIS = ("nome", "filial_id", "filiais", "papel", "ativo", "especialidades")
# Senha temporária gerada (prompt 34): sem caracteres parecidos (0/O/o, 1/l/I/i).
ALFABETO_TEMPORARIA = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
TAMANHO_TEMPORARIA = 14
MSG_FILIAL_PADRAO = "A filial padrão precisa ser uma das filiais permitidas."
MSG_SEM_FILIAL = "Escolha pelo menos uma filial."
MSG_ESPECIALIDADES = "Só quem é da manutenção tem especialidades."
MSG_REGRA_SENHA = (
    f"A senha deve ter pelo menos {senhas.SENHA_MIN} caracteres e ser diferente do login."
)
MSG_ULTIMO_ADMIN = "É preciso manter pelo menos um administrador ativo."
SENHA_REDEFINIDA = "senha redefinida"
SENHA_ALTERADA = "senha alterada"

_ROTULO_CAMPO = {
    "filial_id": "filial padrão",
    "ativo": "ativo",
    "nome": "nome",
    "papel": "papel",
}


@dataclass(frozen=True)
class UsuarioDTO:
    id: int
    nome: str
    login: str
    filial_id: int
    filial_codigo: str
    papel: str
    ativo: bool
    is_gerente: bool
    deve_trocar_senha: bool
    versao: int
    filiais: tuple[int, ...] = ()  # permitidas (com a padrão)
    filiais_codigos: tuple[str, ...] = ()
    email: str | None = None  # prompt 32 (só para o administrador)
    email_confirmado: bool = False
    especialidades: tuple[int, ...] = ()  # prompt 37 (só manutenção)
    especialidades_nomes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SenhaGerada:
    """Devolvida UMA vez à tela do administrador, para entregar ao usuário. Nunca vai
    para log nem e-mail; o banco guarda só o hash."""

    usuario: UsuarioDTO
    senha_temporaria: str

    def __repr__(self) -> str:
        return f"SenhaGerada(usuario_id={self.usuario.id}, senha_temporaria='***')"


@dataclass(frozen=True)
class EventoUsuarioDTO:
    data_hora: datetime
    autor: str  # nome de quem fez, ou 'linha de comando'
    campo: str
    valor_antigo: str | None
    valor_novo: str | None


# --- Validação (pura) ------------------------------------------------------------------


def gerar_senha_temporaria() -> str:
    """14 caracteres do módulo secrets, sem 0/O/o nem 1/l/I/i, com pelo menos uma
    maiúscula, uma minúscula e um dígito."""
    while True:
        senha = "".join(secrets.choice(ALFABETO_TEMPORARIA) for _ in range(TAMANHO_TEMPORARIA))
        if (
            any(c.isupper() for c in senha)
            and any(c.islower() for c in senha)
            and any(c.isdigit() for c in senha)
        ):
            return senha


def validar_senha_nova(senha: object, login: str | None) -> str:
    """Pelo menos 10 caracteres (até o máximo do hash) e diferente do login."""
    if not isinstance(senha, str) or not senhas.SENHA_MIN <= len(senha) <= senhas.SENHA_MAX:
        raise ErroValidacao("senha", MSG_REGRA_SENHA)
    if login is not None and senha.strip().lower() == login.strip().lower():
        raise ErroValidacao("senha", MSG_REGRA_SENHA)
    return senha


def _validar_nome(valor: object) -> str:
    if not isinstance(valor, str) or not 1 <= len(valor.strip()) <= NOME_MAX:
        raise ErroValidacao("nome", f"O nome deve ter de 1 a {NOME_MAX} caracteres.")
    return valor.strip()


def _validar_login(valor: object) -> str:
    import re

    if not isinstance(valor, str) or not re.fullmatch(
        rf"[a-z0-9._-]{{3,{LOGIN_MAX}}}", valor.strip().lower()
    ):
        raise ErroValidacao(
            "login",
            f"O login deve ter de 3 a {LOGIN_MAX} caracteres: letras, números, ponto, "
            "hífen ou sublinhado.",
        )
    return valor.strip().lower()


def _validar_papel(valor: object) -> str:
    if valor not in PAPEIS:
        raise ErroValidacao("papel", "Papel inválido. Use usuario, manutencao ou admin.")
    return valor


def _e_int(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


# --- Núcleo (sessão aberta; também usado pela linha de comando) -----------------------


def _registrar(s: Session, autor_id, usuario_id, campo, antigo, novo, agora) -> None:
    s.add(
        UsuarioEvento(
            admin_id=autor_id,
            usuario_id=usuario_id,
            data_hora=agora,
            campo=campo,
            valor_antigo=None if antigo is None else str(antigo)[:200],
            valor_novo=None if novo is None else str(novo)[:200],
        )
    )


def _filial(s: Session, filial_id: object) -> Filial:
    filial = FilialRepo(s).obter(filial_id) if _e_int(filial_id) else None
    if filial is None:
        raise ErroValidacao("filial_id", "Filial não encontrada.")
    return filial


def _filiais(s: Session, filiais: object, padrao: int) -> list[Filial]:
    """Filiais permitidas (ids) validadas; a padrão entra sempre e precisa estar nelas."""
    if filiais is None:
        filiais = [padrao]
    if not isinstance(filiais, list | tuple | set | frozenset) or not all(
        _e_int(f) for f in filiais
    ):
        raise ErroValidacao("filiais", "Filiais inválidas.")
    if not filiais:
        raise ErroValidacao("filiais", MSG_SEM_FILIAL)
    if padrao not in filiais:
        raise ErroValidacao("filial_id", MSG_FILIAL_PADRAO)
    return sorted((_filial(s, f) for f in set(filiais)), key=lambda f: f.codigo)


def _especialidades(s: Session, valor: object) -> list:
    from osapp.repositories import EspecialidadeRepo

    if not isinstance(valor, list | tuple | set | frozenset) or not all(_e_int(v) for v in valor):
        raise ErroValidacao("especialidades", "Especialidades inválidas.")
    repo = EspecialidadeRepo(s)
    escolhidas = []
    for i in sorted(set(valor)):
        e = repo.obter(i)
        if e is None:
            raise ErroValidacao("especialidades", "Especialidade não encontrada.")
        escolhidas.append(e)
    return escolhidas


def _codigos(filiais) -> str:
    return ", ".join(f.codigo for f in sorted(filiais, key=lambda f: f.codigo))


def _garantir_admin_restante(s: Session, usuario: Usuario, papel: str, ativo: bool) -> None:
    """O último administrador ativo não deixa de ser administrador nem se desativa."""
    deixa_de_ser = usuario.papel == "admin" and usuario.ativo and (papel != "admin" or not ativo)
    if not deixa_de_ser:
        return
    outros = s.scalar(
        select(func.count())
        .select_from(Usuario)
        .where(Usuario.papel == "admin", Usuario.ativo.is_(True), Usuario.id != usuario.id)
    )
    if not outros:
        raise ErroValidacao("papel" if papel != "admin" else "ativo", MSG_ULTIMO_ADMIN)


def criar(
    s: Session,
    autor_id: int | None,
    nome: object,
    login: object,
    filial_id: object,
    papel: object,
    senha: object,
    is_gerente: bool = False,
    temporaria: bool = True,
    filiais: object = None,
) -> Usuario:
    nome = _validar_nome(nome)
    login = _validar_login(login)
    papel = _validar_papel(papel)
    validar_senha_nova(senha, login)
    if not isinstance(is_gerente, bool) or (is_gerente and papel == "admin"):
        raise ErroValidacao("perfil", "Escolha um único perfil: usuário, gerente ou administrador.")
    filial = _filial(s, filial_id)
    permitidas = _filiais(s, filiais, filial.id)
    repo = UsuarioRepo(s)
    if repo.obter_por_login(login) is not None:  # logins são guardados em minúsculas
        raise ErroConflito()
    usuario = repo.adicionar(
        Usuario(
            nome=nome,
            login=login,
            senha_hash=senhas.gerar_hash(senha),
            filial_id=filial.id,
            papel=papel,
            is_gerente=is_gerente,
            deve_trocar_senha=temporaria,
        )
    )
    usuario.filiais = permitidas
    s.flush()
    agora = relogio.agora()
    _registrar(
        s, autor_id, usuario.id, "criacao", None, f"{login} | {filial.codigo} | {papel}", agora
    )
    if len(permitidas) > 1:
        _registrar(s, autor_id, usuario.id, "filiais", None, _codigos(permitidas), agora)
    logger.info("Usuário criado: usuario_id=%s por admin_id=%s.", usuario.id, autor_id)
    return usuario


def alterar(s: Session, autor_id: int | None, usuario: Usuario, alteracoes: dict) -> int:
    """Aplica nome, filial_id (padrão), filiais (permitidas), papel, ativo e gerente.
    Devolve quantos campos mudaram. Desativar revoga os 'Lembrar de mim'."""
    if not isinstance(alteracoes, dict) or not set(alteracoes) <= {*CAMPOS_ALTERAVEIS, "gerente"}:
        raise ErroValidacao("alteracoes", "Dados inválidos.")
    novos: dict = {}
    if "nome" in alteracoes:
        novos["nome"] = _validar_nome(alteracoes["nome"])
    if "filial_id" in alteracoes:
        novos["filial_id"] = _filial(s, alteracoes["filial_id"]).id
    padrao = novos.get("filial_id", usuario.filial_id)
    novas_filiais = None
    if "filiais" in alteracoes:
        novas_filiais = _filiais(s, alteracoes["filiais"], padrao)
    elif padrao not in usuario.filiais_ids:
        raise ErroValidacao("filial_id", MSG_FILIAL_PADRAO)
    if "papel" in alteracoes:
        novos["papel"] = _validar_papel(alteracoes["papel"])
    if "ativo" in alteracoes:
        if not isinstance(alteracoes["ativo"], bool):
            raise ErroValidacao("ativo", "Valor inválido.")
        novos["ativo"] = alteracoes["ativo"]
    if "gerente" in alteracoes:
        if not isinstance(alteracoes["gerente"], bool):
            raise ErroValidacao("gerente", "Valor inválido.")
        novos["is_gerente"] = alteracoes["gerente"]
    papel_final = novos.get("papel", usuario.papel)
    if papel_final == "admin" and novos.get("is_gerente", usuario.is_gerente):
        novos["is_gerente"] = False  # administrador prevalece sobre gerente
    _garantir_admin_restante(s, usuario, papel_final, novos.get("ativo", usuario.ativo))

    agora = relogio.agora()
    # Primeiro os textos do histórico (consultas), depois as mudanças: um só UPDATE e um
    # só incremento de versão.
    mudancas_texto = []
    for campo, novo in novos.items():
        antigo = getattr(usuario, campo)
        if antigo == novo:
            continue
        if campo == "filial_id":
            textos = (usuario.filial.codigo, FilialRepo(s).obter(novo).codigo)
        else:
            textos = (antigo, novo)
        rotulo = "gerente" if campo == "is_gerente" else _ROTULO_CAMPO[campo]
        mudancas_texto.append((campo, novo, rotulo, *textos))
    for campo, novo, *_resto in mudancas_texto:
        setattr(usuario, campo, novo)
    for _campo, _novo, rotulo, texto_antigo, texto_novo in mudancas_texto:
        _registrar(s, autor_id, usuario.id, rotulo, texto_antigo, texto_novo, agora)
    mudancas = len(mudancas_texto)
    # Prompt 37: especialidades só para manutenção; mudar de papel as apaga.
    novas_esp = None
    if "especialidades" in alteracoes:
        novas_esp = _especialidades(s, alteracoes["especialidades"])
        if novas_esp and papel_final != "manutencao":
            raise ErroValidacao("especialidades", MSG_ESPECIALIDADES)
    elif papel_final != "manutencao" and usuario.especialidades:
        novas_esp = []
    if novas_esp is not None:
        antes_esp = list(usuario.especialidades)
        if {e.id for e in antes_esp} != {e.id for e in novas_esp}:
            usuario.especialidades = novas_esp
            _registrar(
                s,
                autor_id,
                usuario.id,
                "especialidades",
                ", ".join(e.nome for e in antes_esp) or None,
                ", ".join(e.nome for e in novas_esp) or None,
                agora,
            )
            mudancas += 1
    if novas_filiais is not None:
        antes = list(usuario.filiais) or [usuario.filial]
        if {f.id for f in antes} != {f.id for f in novas_filiais}:
            usuario.filiais = novas_filiais
            _registrar(
                s, autor_id, usuario.id, "filiais", _codigos(antes), _codigos(novas_filiais), agora
            )
            mudancas += 1
    if novos.get("ativo") is False and "ativo" in [m[0] for m in mudancas_texto]:
        sessoes_lembradas.revogar_sessoes_lembradas(usuario.id, s)
    if mudancas:
        s.flush()
        s.refresh(usuario)
        logger.info("Usuário alterado: usuario_id=%s por admin_id=%s.", usuario.id, autor_id)
    return mudancas


def redefinir(
    s: Session, autor_id: int | None, usuario: Usuario, senha: object, temporaria: bool = True
) -> None:
    """Nova senha (temporária: trocar no próximo login) e zera o atraso daquele login."""
    validar_senha_nova(senha, usuario.login)
    usuario.senha_hash = senhas.gerar_hash(senha)
    usuario.deve_trocar_senha = temporaria
    TentativaLoginRepo(s).apagar(TIPO_LOGIN, protecao_login.chave_do_login(usuario.login))
    sessoes_lembradas.revogar_sessoes_lembradas(usuario.id, s)
    _registrar(s, autor_id, usuario.id, "senha", None, SENHA_REDEFINIDA, relogio.agora())
    s.flush()
    logger.info("Senha redefinida: usuario_id=%s por admin_id=%s.", usuario.id, autor_id)


# --- Leitura ---------------------------------------------------------------------------


def _dto(u: Usuario, notificacao: UsuarioNotificacao | None = None) -> UsuarioDTO:
    filiais = sorted({f.id: f for f in [*u.filiais, u.filial]}.values(), key=lambda f: f.codigo)
    return UsuarioDTO(
        u.id,
        u.nome,
        u.login,
        u.filial_id,
        u.filial.codigo,
        u.papel,
        u.ativo,
        u.is_gerente,
        u.deve_trocar_senha,
        u.versao,
        filiais=tuple(f.id for f in filiais),
        filiais_codigos=tuple(f.codigo for f in filiais),
        email=notificacao.email if notificacao else None,
        email_confirmado=bool(notificacao and notificacao.email_confirmado_em),
        especialidades=tuple(e.id for e in u.especialidades),
        especialidades_nomes=tuple(e.nome for e in u.especialidades),
    )


def _dto_completo(s: Session, u: Usuario) -> UsuarioDTO:
    return _dto(u, s.get(UsuarioNotificacao, u.id))


def _admin(ator_id: int):
    ator = carregar_ator(ator_id)
    try:
        exigir_admin(ator)
    except ErroPermissao:
        logger.warning("Permissão negada: usuario_id=%s ação=gestão de usuários.", ator.usuario_id)
        raise
    return ator


def _carregar(s: Session, usuario_id: object) -> Usuario:
    usuario = UsuarioRepo(s).obter(usuario_id) if _e_int(usuario_id) else None
    if usuario is None:
        raise ErroNaoEncontrado()
    return usuario


def listar_usuarios(
    ator_id: int,
    busca: str | None = None,
    papel: str | None = None,
    filial_id: int | None = None,
    ativo: bool | None = None,
) -> list[UsuarioDTO]:
    """Busca por nome ou login; filtros por papel, filial e ativo. Só administrador."""
    _admin(ator_id)
    if busca is not None and not isinstance(busca, str):
        raise ErroValidacao("busca", "Busca inválida.")
    if papel is not None:
        _validar_papel(papel)
    if filial_id is not None and not _e_int(filial_id):
        raise ErroValidacao("filial_id", "Filial inválida.")
    if ativo is not None and not isinstance(ativo, bool):
        raise ErroValidacao("ativo", "Valor inválido.")
    busca = (busca or "").strip()[:BUSCA_MAX]
    consulta = select(Usuario).order_by(Usuario.nome, Usuario.id)
    if busca:
        consulta = consulta.where(
            or_(
                Usuario.nome.icontains(busca, autoescape=True),
                Usuario.login.icontains(busca, autoescape=True),
            )
        )
    if papel is not None:
        consulta = consulta.where(Usuario.papel == papel)
    if filial_id is not None:  # padrão ou permitida
        consulta = consulta.where(
            or_(Usuario.filial_id == filial_id, Usuario.filiais.any(Filial.id == filial_id))
        )
    if ativo is not None:
        consulta = consulta.where(Usuario.ativo.is_(ativo))
    with sessao() as s:
        return [_dto_completo(s, u) for u in s.scalars(consulta)]


def obter_usuario(ator_id: int, usuario_id: int) -> UsuarioDTO:
    _admin(ator_id)
    with sessao() as s:
        return _dto_completo(s, _carregar(s, usuario_id))


def listar_eventos_usuario(ator_id: int, usuario_id: int) -> list[EventoUsuarioDTO]:
    _admin(ator_id)
    with sessao() as s:
        usuario = _carregar(s, usuario_id)
        eventos = s.scalars(
            select(UsuarioEvento)
            .where(UsuarioEvento.usuario_id == usuario.id)
            .order_by(UsuarioEvento.data_hora, UsuarioEvento.id)
        )
        return [
            EventoUsuarioDTO(
                e.data_hora,
                e.admin.nome if e.admin else "linha de comando",
                e.campo,
                e.valor_antigo,
                e.valor_novo,
            )
            for e in eventos
        ]


# --- Escrita (interface) -----------------------------------------------------------------


def criar_usuario(
    ator_id: int,
    nome: str,
    login: str,
    filial_id: int,
    papel: str,
    filiais: list[int] | None = None,
) -> SenhaGerada:
    """Cria com senha temporária GERADA (devolvida uma vez para a tela). ``filial_id``:
    a filial padrão; ``filiais``: as permitidas (padrão: só a padrão)."""
    ator = _admin(ator_id)
    senha = gerar_senha_temporaria()
    with sessao() as s:
        usuario = criar(s, ator.usuario_id, nome, login, filial_id, papel, senha, filiais=filiais)
        return SenhaGerada(_dto_completo(s, usuario), senha)


def alterar_usuario(ator_id: int, usuario_id: int, versao: int, alteracoes: dict) -> UsuarioDTO:
    """Nome, filial_id (padrão), filiais (permitidas), papel e ativo. Versão
    desatualizada: ErroConflito."""
    ator = _admin(ator_id)
    try:
        with sessao() as s:
            usuario = _carregar(s, usuario_id)
            if not _e_int(versao) or versao != usuario.versao:
                raise ErroConflito()
            if not isinstance(alteracoes, dict) or not set(alteracoes) <= set(CAMPOS_ALTERAVEIS):
                raise ErroValidacao("alteracoes", "Dados inválidos.")
            alterar(s, ator.usuario_id, usuario, alteracoes)
            return _dto_completo(s, usuario)
    except StaleDataError:
        raise ErroConflito() from None


def redefinir_senha(ator_id: int, usuario_id: int, versao: int) -> SenhaGerada:
    """O sistema GERA a senha temporária (devolvida uma vez para a tela), guarda só o
    hash, marca a troca obrigatória e revoga os 'Lembrar de mim'."""
    ator = _admin(ator_id)
    senha = gerar_senha_temporaria()
    try:
        with sessao() as s:
            usuario = _carregar(s, usuario_id)
            if not _e_int(versao) or versao != usuario.versao:
                raise ErroConflito()
            redefinir(s, ator.usuario_id, usuario, senha)
            s.refresh(usuario)
            return SenhaGerada(_dto_completo(s, usuario), senha)
    except StaleDataError:
        raise ErroConflito() from None


def trocar_propria_senha(ator_id: int, senha_atual: str, senha_nova: str) -> None:
    """Qualquer usuário: confere a senha atual, aplica a regra e tira a troca obrigatória."""
    ator = carregar_ator(ator_id)
    with sessao() as s:
        usuario = _carregar(s, ator.usuario_id)
        if not isinstance(senha_atual, str) or not senhas.verificar(
            senha_atual, usuario.senha_hash
        ):
            logger.warning("Troca de senha recusada: usuario_id=%s senha atual errada.", usuario.id)
            raise ErroValidacao("senha_atual", "A senha atual não confere.")
        validar_senha_nova(senha_nova, usuario.login)
        if senhas.verificar(senha_nova, usuario.senha_hash):
            raise ErroValidacao("senha", "A nova senha deve ser diferente da atual.")
        usuario.senha_hash = senhas.gerar_hash(senha_nova)
        usuario.deve_trocar_senha = False
        sessoes_lembradas.revogar_sessoes_lembradas(usuario.id, s)
        _registrar(s, usuario.id, usuario.id, "senha", None, SENHA_ALTERADA, relogio.agora())
        logger.info("Senha alterada pelo próprio usuário: usuario_id=%s.", usuario.id)
