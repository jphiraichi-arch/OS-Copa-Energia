"""Núcleo de permissões: papel de administrador e acesso por filial."""

from __future__ import annotations

from osapp.services.auth import Ator
from osapp.services.erros import ErroPermissao


def exigir_admin(ator: Ator) -> None:
    if not ator.is_admin:
        raise ErroPermissao()


def pode_acessar_filial(ator: Ator, filial_id: int) -> bool:
    """Administrador acessa qualquer filial; os demais, apenas a própria."""
    return ator.is_admin or ator.filial_id == filial_id


def pode_usar_lixeira(ator: Ator) -> bool:
    """Excluir, restaurar e ver as ordens excluídas: só o administrador (prompt 24)."""
    return ator.is_admin


def pode_ver_relatorio_mensal(ator: Ator, filial_id: int | None) -> bool:
    """Relatório mensal, com custos (decisão de 21/11/2026).

    Administrador: qualquer filial e o consolidado (``filial_id`` None).
    Manutenção: só a própria filial. Papel usuario: nunca. O sinalizador de gerente não
    muda mais o acesso.
    """
    if ator.is_admin:
        return True
    return ator.is_manutencao and filial_id == ator.filial_id
