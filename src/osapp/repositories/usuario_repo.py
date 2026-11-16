from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from osapp.models import Usuario


class UsuarioRepo:
    def __init__(self, sessao: Session) -> None:
        self._s = sessao

    def obter(self, usuario_id: int) -> Usuario | None:
        return self._s.get(Usuario, usuario_id)

    def obter_por_login(self, login: str) -> Usuario | None:
        return self._s.scalars(select(Usuario).where(Usuario.login == login.lower())).one_or_none()

    def adicionar(self, usuario: Usuario) -> Usuario:
        self._s.add(usuario)
        self._s.flush()
        return usuario
