"""Núcleo de permissões: papel de administrador e acesso por filial."""

from __future__ import annotations

from osapp.services.auth import Ator
from osapp.services.erros import ErroPermissao


def exigir_admin(ator: Ator) -> None:
    if not ator.e_admin:
        raise ErroPermissao()


def pode_acessar_filial_do_papel(papel: str, filiais_do_usuario, filial_id: int) -> bool:
    """Administrador acessa qualquer filial; os demais, só as filiais permitidas
    (prompts 28 e 34). Usada também sem um Ator carregado, por exemplo para escolher os
    destinatários de um e-mail. ``filiais_do_usuario``: um id ou uma coleção de ids."""
    if papel == "admin":
        return True
    if isinstance(filiais_do_usuario, int):
        return filiais_do_usuario == filial_id
    return filial_id in filiais_do_usuario


def pode_acessar_filial(ator: Ator, filial_id: int) -> bool:
    """Administrador acessa qualquer filial; os demais, só as permitidas."""
    return pode_acessar_filial_do_papel(ator.papel, ator.filiais, filial_id)


def pode_usar_lixeira(ator: Ator) -> bool:
    """Excluir, restaurar e ver as ordens excluídas: só o administrador (prompt 24)."""
    return ator.e_admin


def pode_ver_relatorio_mensal(ator: Ator, filial_id: int | None) -> bool:
    """Relatório mensal, com custos (decisão de 21/11/2026).

    Administrador: qualquer filial e o consolidado (``filial_id`` None).
    Manutenção: só as filiais permitidas (prompt 34). Papel usuario: nunca. O
    sinalizador de gerente não muda mais o acesso.
    """
    if ator.e_admin:
        return True
    return ator.e_manutencao and filial_id in ator.filiais
