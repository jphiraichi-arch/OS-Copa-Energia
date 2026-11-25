"""Motivos de cancelamento (prompt 41), com as mesmas regras da lista de especialidades.

Gerado a partir de services/especialidades.py (mesma API: listar, criar, alterar,
mover). Todos os papéis leem os ativos (quem cancela escolhe um).

Original: Lista de especialidades (prompt 37).

- Manutenção e administrador leem a lista (o papel usuario nunca: ErroPermissao).
- Só o administrador cria, renomeia, desativa/reativa e muda a ordem. Desativada não é
  escolhida em OS nova, mas continua nas antigas (a validação fica em services/ordens).
- Toda mudança vai para o log do servidor com o id do administrador.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from osapp.db import sessao
from osapp.models import MotivoCancelamento as Especialidade
from osapp.repositories import MotivoCancelamentoRepo as EspecialidadeRepo
from osapp.services.auth import carregar_ator
from osapp.services.erros import ErroConflito, ErroNaoEncontrado, ErroValidacao
from osapp.services.permissoes import exigir_admin

logger = logging.getLogger(__name__)

NOME_MAX = 60
MSG_NOME = f"O nome deve ter de 2 a {NOME_MAX} caracteres."


@dataclass(frozen=True)
class MotivoDTO:
    id: int
    codigo: str
    nome: str
    ordem: int
    ativo: bool


def _dto(e: Especialidade) -> MotivoDTO:
    return MotivoDTO(e.id, e.codigo, e.nome, e.ordem, e.ativo)


def _validar_nome(valor: object) -> str:
    if not isinstance(valor, str) or not 2 <= len(valor.strip()) <= NOME_MAX:
        raise ErroValidacao("nome", MSG_NOME)
    return " ".join(valor.split())


def _codigo(nome: str) -> str:
    """'Predial/civil' -> 'PREDIAL_CIVIL' (sem acentos)."""
    import unicodedata

    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "_", sem_acento.upper()).strip("_")[:30] or "MOTIVO"


def listar(ator_id: int, incluir_inativas: bool = False) -> list[MotivoDTO]:
    ator = carregar_ator(ator_id)
    if incluir_inativas:
        exigir_admin(ator)
    with sessao() as s:
        return [_dto(e) for e in EspecialidadeRepo(s).listar(so_ativas=not incluir_inativas)]


def criar(ator_id: int, nome: object) -> MotivoDTO:
    ator = carregar_ator(ator_id)
    exigir_admin(ator)
    nome = _validar_nome(nome)
    try:
        with sessao() as s:
            repo = EspecialidadeRepo(s)
            todas = repo.listar(so_ativas=False)
            if any(e.nome.casefold() == nome.casefold() for e in todas):
                raise ErroValidacao("nome", "Já existe um motivo com este nome.")
            codigo = _codigo(nome)
            if repo.obter_por_codigo(codigo) is not None:
                codigo = f"{codigo[:25]}_{len(todas) + 1}"
            nova = repo.adicionar(
                Especialidade(
                    codigo=codigo, nome=nome, ordem=max((e.ordem for e in todas), default=0) + 1
                )
            )
            logger.info(
                "Motivo de cancelamento criado: id=%s por admin_id=%s.", nova.id, ator.usuario_id
            )
            return _dto(nova)
    except IntegrityError:
        raise ErroConflito() from None


def alterar(
    ator_id: int,
    especialidade_id: object,
    nome: object = None,
    ativo: object = None,
) -> MotivoDTO:
    """Renomeia e/ou ativa/desativa."""
    ator = carregar_ator(ator_id)
    exigir_admin(ator)
    with sessao() as s:
        repo = EspecialidadeRepo(s)
        e = repo.obter(especialidade_id) if isinstance(especialidade_id, int) else None
        if e is None:
            raise ErroNaoEncontrado()
        if nome is not None:
            novo = _validar_nome(nome)
            if any(
                o.id != e.id and o.nome.casefold() == novo.casefold()
                for o in repo.listar(so_ativas=False)
            ):
                raise ErroValidacao("nome", "Já existe um motivo com este nome.")
            e.nome = novo
        if ativo is not None:
            if not isinstance(ativo, bool):
                raise ErroValidacao("ativo", "Valor inválido.")
            e.ativo = ativo
        logger.info(
            "Motivo de cancelamento alterado: id=%s nome=%s ativo=%s por admin_id=%s.",
            e.id,
            nome is not None,
            e.ativo,
            ator.usuario_id,
        )
        return _dto(e)


def mover(ator_id: int, especialidade_id: object, direcao: object) -> list[MotivoDTO]:
    """Troca a posição com a vizinha (direcao -1 sobe, +1 desce). Devolve a lista."""
    ator = carregar_ator(ator_id)
    exigir_admin(ator)
    if direcao not in (-1, 1):
        raise ErroValidacao("direcao", "Direção inválida.")
    with sessao() as s:
        todas = EspecialidadeRepo(s).listar(so_ativas=False)
        posicao = next((i for i, e in enumerate(todas) if e.id == especialidade_id), None)
        if posicao is None:
            raise ErroNaoEncontrado()
        vizinha = posicao + direcao
        if 0 <= vizinha < len(todas):
            todas[posicao], todas[vizinha] = todas[vizinha], todas[posicao]
            for i, e in enumerate(todas, start=1):
                e.ordem = i
            logger.info("Motivos de cancelamento reordenados por admin_id=%s.", ator.usuario_id)
        return [_dto(e) for e in todas]
