"""Formatação e leitura de valores no padrão brasileiro.

Funções puras: sem Flet e sem depender do locale do servidor.
Armazenamento: dinheiro em centavos (int), durações em minutos (int), instantes em UTC.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from osapp import config

NBSP = "\u00a0"  # espaço que não quebra: une as partes de um valor
MENOS = "\u2212"  # sinal de menos tipográfico (percentuais com sinal)

_RE_BRL = re.compile(r"^(?:R\$\s*)?(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d{2}))?$")
_RE_QUANTIDADE = re.compile(r"^(\d{1,5})(?:,(\d{1,2}))?$")
_RE_DURACAO = re.compile(r"^(\d{1,4}):([0-5]\d)$")


def _exigir_int(valor: object, nome: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise TypeError(f"{nome} deve ser int, recebido {type(valor).__name__}")
    return valor


def _fuso(tz: str | None) -> ZoneInfo:
    return ZoneInfo(tz or config.fuso())


def _no_fuso(dt: datetime, tz: str | None) -> datetime:
    """Converte para o fuso da aplicação. Datetime sem fuso é tratado como UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(_fuso(tz))


def formatar_brl(centavos: int) -> str:
    """123456 -> 'R$\u00a01.234,56'. Negativos: '-R$\u00a01.234,56'.

    As partes de um valor são unidas por espaço que não quebra (U+00A0, ``NBSP``): na
    tela, o valor nunca se parte no meio (prompt 26).
    """
    _exigir_int(centavos, "centavos")
    reais, resto = divmod(abs(centavos), 100)
    inteiro = f"{reais:,}".replace(",", ".")
    sinal = "-" if centavos < 0 else ""
    return f"{sinal}R${NBSP}{inteiro},{resto:02d}"


def formatar_percentual(valor: float, sinal: bool = False) -> str:
    """12.5 -> '12,5%'; 30.0 -> '30%'; 33.333 -> '33,3%' (uma casa, sem ',0'; sem espaço).

    ``sinal``: '+12%' ou '\u221212%' (sinal de menos tipográfico). Zero nunca leva sinal.
    """
    arredondado = round(float(valor), 1)
    texto = f"{abs(arredondado):.1f}".replace(".", ",").removesuffix(",0")
    if sinal and arredondado > 0:
        return f"+{texto}%"
    if arredondado < 0:
        return f"{MENOS}{texto}%"
    return f"{texto}%"


def ler_brl(texto: str) -> int:
    """Lê '150', '150,50', '1.234,56' ou 'R$ 1.234,56' e devolve centavos.

    Sem vírgula, o número é em reais ('150' = R$ 150,00). O ponto só separa milhares:
    '150.50' é recusado, para não confundir com o formato americano.
    """
    if not isinstance(texto, str):
        raise ValueError("Valor inválido.")
    m = _RE_BRL.match(texto.replace("\u00a0", " ").strip())
    if not m:
        raise ValueError(f"Valor inválido: {texto!r}. Use o formato 1.234,56.")
    return int(m.group(1).replace(".", "")) * 100 + int(m.group(2) or 0)


def ler_quantidade(texto: str) -> Decimal:
    """Lê '1', '1,5' ou '1,50' e devolve um Decimal com 2 casas. '1.5' é recusado."""
    if not isinstance(texto, str):
        raise ValueError("Quantidade inválida.")
    m = _RE_QUANTIDADE.match(texto.strip())
    if not m:
        raise ValueError(f"Quantidade inválida: {texto!r}. Use o formato 1,5.")
    return Decimal(f"{m.group(1)}.{(m.group(2) or '').ljust(2, '0')}")


def formatar_quantidade(quantidade: Decimal) -> str:
    """Decimal('1.50') -> '1,5'; Decimal('2.00') -> '2'; Decimal('0.25') -> '0,25'."""
    texto = f"{Decimal(quantidade):.2f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",")


def formatar_data(dt: date | datetime, tz: str | None = None) -> str:
    """'dd/mm/aaaa'. Um datetime é convertido antes para o fuso OS_TZ; um date não muda."""
    if isinstance(dt, datetime):
        dt = _no_fuso(dt, tz)
    return f"{dt.day:02d}/{dt.month:02d}/{dt.year:04d}"


def formatar_data_hora(dt: datetime, tz: str | None = None) -> str:
    """'dd/mm/aaaa HH:MM' no fuso OS_TZ (ou ``tz``). Datetime sem fuso é tratado como UTC."""
    local = _no_fuso(dt, tz)
    return (
        f"{local.day:02d}/{local.month:02d}/{local.year:04d}{NBSP}"
        f"{local.hour:02d}:{local.minute:02d}"
    )


def formatar_duracao(minutos: int) -> str:
    """90 -> '1h30'; 0 -> '0h00'."""
    _exigir_int(minutos, "minutos")
    if minutos < 0:
        raise ValueError("Duração não pode ser negativa.")
    horas, resto = divmod(minutos, 60)
    return f"{horas}h{resto:02d}"


def formatar_tempo(segundos: int) -> str:
    """Duração de atendimento: '45 min', '3 h 20 min', '2 d 4 h'.

    Arredonda para o minuto mais próximo (meio para cima). A partir de 1 dia mostra só
    dias e horas (horas inteiras, sem os minutos que sobram).
    """
    _exigir_int(segundos, "segundos")
    if segundos < 0:
        raise ValueError("Duração não pode ser negativa.")
    minutos = (segundos + 30) // 60
    if minutos < 60:
        return f"{minutos}{NBSP}min"
    if minutos < 24 * 60:
        horas, resto = divmod(minutos, 60)
        return f"{horas}{NBSP}h{NBSP}{resto}{NBSP}min" if resto else f"{horas}{NBSP}h"
    dias, resto = divmod(minutos, 24 * 60)
    horas = resto // 60
    return f"{dias}{NBSP}d{NBSP}{horas}{NBSP}h" if horas else f"{dias}{NBSP}d"


def ler_duracao(texto: str) -> int:
    """Lê '1:30' ou '01:30' (horas:minutos) e devolve minutos."""
    if not isinstance(texto, str):
        raise ValueError("Duração inválida.")
    m = _RE_DURACAO.match(texto.strip())
    if not m:
        raise ValueError(f"Duração inválida: {texto!r}. Use o formato H:MM, por exemplo 1:30.")
    return int(m.group(1)) * 60 + int(m.group(2))
