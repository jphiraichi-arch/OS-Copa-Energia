"""Tipos de coluna próprios do projeto."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class DataHoraUTC(TypeDecorator):
    """Instante sempre gravado em UTC e sempre lido como datetime com fuso UTC.

    O SQLite descarta o fuso; por isso o valor é convertido para UTC antes de gravar
    e o fuso UTC é recolocado na leitura. Datetime sem fuso é recusado na gravação.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError("DataHoraUTC exige datetime.")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("DataHoraUTC exige datetime com fuso horário.")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
