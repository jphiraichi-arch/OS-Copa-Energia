"""Equipamentos das filiais.

Leitura para quem cria ou edita OS; cadastro e desativação só por administrador
(pela CLI, informando o login do administrador responsável).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from osapp.db import sessao
from osapp.models import Equipamento
from osapp.repositories import EquipamentoRepo, FilialRepo, UsuarioRepo
from osapp.services.auth import carregar_ator
from osapp.services.erros import ErroNaoEncontrado, ErroPermissao, ErroValidacao
from osapp.services.permissoes import pode_acessar_filial

logger = logging.getLogger(__name__)

NOME_MAX = 120
CODIGO_SAP_MAX = 40


@dataclass(frozen=True)
class EquipamentoDTO:
    id: int
    filial_id: int
    nome: str
    codigo_sap: str | None
    ativo: bool


def _dto(e: Equipamento) -> EquipamentoDTO:
    return EquipamentoDTO(e.id, e.filial_id, e.nome, e.codigo_sap, e.ativo)


def listar_equipamentos(ator_id: int, filial_id: int | None = None) -> list[EquipamentoDTO]:
    """Equipamentos ativos da filial (padrão: a do ator) que o ator pode usar."""
    ator = carregar_ator(ator_id)
    if filial_id is None:
        filial_id = ator.filial_id
    if isinstance(filial_id, bool) or not isinstance(filial_id, int):
        raise ErroValidacao("filial_id", "Filial inválida.")
    if not pode_acessar_filial(ator, filial_id):
        logger.warning(
            "Permissão negada: usuario_id=%s ação=listar equipamentos de outra filial.",
            ator.usuario_id,
        )
        raise ErroPermissao()
    with sessao() as s:
        return [_dto(e) for e in EquipamentoRepo(s).listar(filial_id)]


def _exigir_admin(s, login_responsavel: object):
    usuario = (
        UsuarioRepo(s).obter_por_login(login_responsavel.strip())
        if isinstance(login_responsavel, str)
        else None
    )
    if usuario is None or not usuario.ativo or usuario.papel != "admin":
        raise ErroPermissao()
    return usuario


def criar_equipamento(
    login_responsavel: str, filial_codigo: str, nome: str, codigo_sap: str | None = None
) -> EquipamentoDTO:
    if not isinstance(nome, str) or not 1 <= len(nome.strip()) <= NOME_MAX:
        raise ErroValidacao("nome", f"O nome deve ter de 1 a {NOME_MAX} caracteres.")
    if codigo_sap is not None and (
        not isinstance(codigo_sap, str) or not 1 <= len(codigo_sap.strip()) <= CODIGO_SAP_MAX
    ):
        raise ErroValidacao("codigo_sap", f"O código SAP deve ter até {CODIGO_SAP_MAX} caracteres.")
    with sessao() as s:
        responsavel = _exigir_admin(s, login_responsavel)
        filial = (
            FilialRepo(s).obter_por_codigo(filial_codigo.strip())
            if isinstance(filial_codigo, str)
            else None
        )
        if filial is None:
            raise ErroValidacao("filial", "Filial não encontrada.")
        equipamento = EquipamentoRepo(s).adicionar(
            Equipamento(
                filial_id=filial.id,
                nome=nome.strip(),
                codigo_sap=codigo_sap.strip() if codigo_sap else None,
            )
        )
        logger.info("Equipamento criado: id=%s usuario_id=%s.", equipamento.id, responsavel.id)
        return _dto(equipamento)


def desativar_equipamento(login_responsavel: str, equipamento_id: int) -> EquipamentoDTO:
    """Desativa (não apaga): OS antigas continuam apontando para ele."""
    with sessao() as s:
        responsavel = _exigir_admin(s, login_responsavel)
        equipamento = (
            EquipamentoRepo(s).obter(equipamento_id)
            if isinstance(equipamento_id, int) and not isinstance(equipamento_id, bool)
            else None
        )
        if equipamento is None:
            raise ErroNaoEncontrado()
        equipamento.ativo = False
        logger.info("Equipamento desativado: id=%s usuario_id=%s.", equipamento.id, responsavel.id)
        return _dto(equipamento)
