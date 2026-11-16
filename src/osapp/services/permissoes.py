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
