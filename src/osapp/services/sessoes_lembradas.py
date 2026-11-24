"""Sessões 'Lembrar de mim' (prompt 35).

``revogar_sessoes_lembradas`` é chamada na redefinição de senha pelo administrador, na
troca da própria senha e na desativação do usuário (prompt 34). Até o prompt 35 não há
tokens guardados, então ela não faz nada.
"""

from __future__ import annotations

from sqlalchemy.orm import Session


def revogar_sessoes_lembradas(usuario_id: int, s: Session | None = None) -> int:
    """Revoga todos os tokens 'Lembrar de mim' do usuário. Devolve quantos.

    TODO(prompt 35): marcar revogado_em em sessoes_lembradas.
    """
    del usuario_id, s
    return 0
