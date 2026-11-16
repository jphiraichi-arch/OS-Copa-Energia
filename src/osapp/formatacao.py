"""Formatação e leitura de valores no padrão brasileiro.

Funções puras: sem Flet e sem depender do locale do servidor.
Armazenamento: dinheiro em centavos (int), durações em minutos (int), instantes em UTC.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from osapp.config import TZ_PADRAO

_RE_BRL = re.compile(r"^(?:R\$\s*)?(\d{1,3}(?:\.\d{3})+|\d+),(\d{2})$")
_RE_DURACAO = re.compile(r"^(\d{1,4}):([0-5]\d)$")


def _exigir_int(valor: object, nome: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise TypeError(f"{nome} deve ser int, recebido {type(valor).__name__}")
    return valor


def _fuso(tz: str | None) -> ZoneInfo:
    return ZoneInfo(tz or os.environ.get("OS_TZ") or TZ_PADRAO)


def _no_fuso(dt: datetime, tz: str | None) -> datetime:
    """Converte para o fuso da aplicação. Datetime sem fuso é tratado como UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(_fuso(tz))


def formatar_brl(centavos: int) -> str:
    """123456 -> 'R$ 1.234,56'. Negativos: '-R$ 1.234,56'."""
    _exigir_int(centavos, "centavos")
    reais, resto = divmod(abs(centavos), 100)
    inteiro = f"{reais:,}".replace(",", ".")
    sinal = "-" if centavos < 0 else ""
    return f"{sinal}R$ {inteiro},{resto:02d}"


def ler_brl(texto: str) -> int:
    """Lê '1234,56', '1.234,56' ou 'R$ 1.234,56' e devolve centavos."""
    if not isinstance(texto, str):
        raise ValueError("Valor inválido.")
    m = _RE_BRL.match(texto.replace(" ", " ").strip())
    if not m:
        raise ValueError(f"Valor inválido: {texto!r}. Use o formato 1.234,56.")
    return int(m.group(1).replace(".", "")) * 100 + int(m.group(2))


def formatar_data(dt: date | datetime, tz: str | None = None) -> str:
    """'dd/mm/aaaa'. Um datetime é convertido antes para o fuso OS_TZ; um date não muda."""
    if isinstance(dt, datetime):
        dt = _no_fuso(dt, tz)
    return f"{dt.day:02d}/{dt.month:02d}/{dt.year:04d}"


def formatar_data_hora(dt: datetime, tz: str | None = None) -> str:
    """'dd/mm/aaaa HH:MM' no fuso OS_TZ (ou ``tz``). Datetime sem fuso é tratado como UTC."""
    local = _no_fuso(dt, tz)
    return f"{local.day:02d}/{local.month:02d}/{local.year:04d} {local.hour:02d}:{local.minute:02d}"


def formatar_duracao(minutos: int) -> str:
    """90 -> '1h30'; 0 -> '0h00'."""
    _exigir_int(minutos, "minutos")
    if minutos < 0:
        raise ValueError("Duração não pode ser negativa.")
    horas, resto = divmod(minutos, 60)
    return f"{horas}h{resto:02d}"


def ler_duracao(texto: str) -> int:
    """Lê '1:30' ou '01:30' (horas:minutos) e devolve minutos."""
    if not isinstance(texto, str):
        raise ValueError("Duração inválida.")
    m = _RE_DURACAO.match(texto.strip())
    if not m:
        raise ValueError(f"Duração inválida: {texto!r}. Use o formato H:MM, por exemplo 1:30.")
    return int(m.group(1)) * 60 + int(m.group(2))
