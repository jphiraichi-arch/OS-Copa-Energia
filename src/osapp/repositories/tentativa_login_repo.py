from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from osapp.models import TentativaLogin


class TentativaLoginRepo:
    """Contadores de falhas de login (por login e por IP)."""

    def __init__(self, sessao: Session) -> None:
        self._s = sessao

    def travar(self, tipo: str, chave: str, agora: datetime) -> TentativaLogin:
        """Devolve a linha (criada se faltar) travada até o fim da transação.

        INSERT ... ON CONFLICT DO NOTHING e depois SELECT ... FOR UPDATE: tentativas
        simultâneas para a mesma chave esperam umas pelas outras e nenhuma se perde.
        """
        dialeto = self._s.get_bind().dialect.name
        modulo = postgresql if dialeto == "postgresql" else sqlite
        self._s.execute(
            modulo.insert(TentativaLogin)
            .values(tipo=tipo, chave=chave, falhas=0, atualizado_em=agora)
            .on_conflict_do_nothing(index_elements=["tipo", "chave"])
        )
        return self._s.scalars(
            select(TentativaLogin)
            .where(TentativaLogin.tipo == tipo, TentativaLogin.chave == chave)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one()

    def obter(self, tipo: str, chave: str) -> TentativaLogin | None:
        return self._s.scalars(
            select(TentativaLogin).where(TentativaLogin.tipo == tipo, TentativaLogin.chave == chave)
        ).one_or_none()

    def apagar(self, tipo: str, chave: str) -> int:
        resultado = self._s.execute(
            delete(TentativaLogin).where(TentativaLogin.tipo == tipo, TentativaLogin.chave == chave)
        )
        return resultado.rowcount or 0

    def apagar_anteriores(self, limite: datetime) -> int:
        resultado = self._s.execute(
            delete(TentativaLogin).where(TentativaLogin.atualizado_em < limite)
        )
        return resultado.rowcount or 0
