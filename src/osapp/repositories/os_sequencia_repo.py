from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from osapp.models import OsSequencia


class OsSequenciaRepo:
    """Contador de números de OS por filial e ano."""

    def __init__(self, sessao: Session) -> None:
        self._s = sessao

    def reservar_proximo(self, filial_id: int, ano: int) -> int:
        """Incrementa e devolve o contador, na transação da sessão.

        Cria a linha se faltar (INSERT ... ON CONFLICT DO NOTHING: se duas transações
        tentarem criá-la juntas, uma espera a outra e não há erro) e depois a trava com
        SELECT ... FOR UPDATE até o fim da transação. Se a transação for desfeita, o
        número não é consumido.
        """
        dialeto = self._s.get_bind().dialect.name
        modulo = postgresql if dialeto == "postgresql" else sqlite
        self._s.execute(
            modulo.insert(OsSequencia)
            .values(filial_id=filial_id, ano=ano, ultimo_numero=0)
            .on_conflict_do_nothing(index_elements=["filial_id", "ano"])
        )
        contador = self._s.scalars(
            select(OsSequencia)
            .where(OsSequencia.filial_id == filial_id, OsSequencia.ano == ano)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one()
        contador.ultimo_numero += 1
        self._s.flush()
        return contador.ultimo_numero
