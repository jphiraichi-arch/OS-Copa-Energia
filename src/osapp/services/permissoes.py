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


def pode_ver_relatorio_completo(ator: Ator, filial_id: int | None) -> bool:
    """Relatório completo (valores e desempenho por pessoa).

    Administrador: qualquer filial e o consolidado (``filial_id`` None).
    Gerente: só a própria filial. Demais usuários: nunca.
    """
    if ator.is_admin:
        return True
    return ator.is_gerente and filial_id == ator.filial_id
