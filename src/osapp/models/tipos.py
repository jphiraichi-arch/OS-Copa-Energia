"""Tipos de coluna próprios do projeto."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric
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


CENTESIMOS = Decimal("0.01")


class Quantidade(TypeDecorator):
    """Decimal exato com 2 casas. Nunca float.

    PostgreSQL: NUMERIC(12,2). SQLite (sem decimal exato): inteiro de centésimos.
    Nos dois bancos o valor lido é um ``decimal.Decimal`` igual ao gravado.
    """

    impl = Numeric(12, 2)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(Integer())
        return dialect.type_descriptor(Numeric(12, 2, asdecimal=True))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, Decimal | int):
            raise TypeError("Quantidade exige Decimal ou int (nunca float).")
        valor = Decimal(value)
        if valor != valor.quantize(CENTESIMOS):
            raise ValueError("Quantidade com mais de 2 casas decimais.")
        if dialect.name == "sqlite":
            return int(valor * 100)
        return valor.quantize(CENTESIMOS)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "sqlite":
            return (Decimal(value) / 100).quantize(CENTESIMOS)
        return Decimal(value).quantize(CENTESIMOS)
