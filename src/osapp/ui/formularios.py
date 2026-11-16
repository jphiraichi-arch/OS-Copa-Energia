"""Conversão entre o que o usuário digita e os argumentos dos serviços. Módulo puro.

É só conveniência: a validação que vale é sempre a do serviço.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from osapp import formatacao

MSG_VALOR = "Valor inválido. Use o formato 1.234,56."
MSG_TEMPO = "Tempo inválido. Use o formato H:MM, por exemplo 1:30."
MSG_TEMPO_ZERO = "O tempo deve ser de pelo menos 1 minuto."
MSG_DATA = "Data inválida. Use o formato dd/mm/aaaa."
MSG_HORA = "Hora inválida. Use o formato HH:MM, por exemplo 13:50."

_RE_DATA = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_RE_HORA = re.compile(r"^(\d{1,2}):(\d{2})$")


def ler_valor(texto: str | None) -> int:
    """'1.234,56' -> 123456 centavos. ValueError com mensagem em português."""
    try:
        return formatacao.ler_brl(texto or "")
    except ValueError:
        raise ValueError(MSG_VALOR) from None


def ler_tempo(texto: str | None) -> int:
    """'1:30' -> 90 minutos. ValueError com mensagem em português; '0:00' é recusado."""
    try:
        minutos = formatacao.ler_duracao(texto or "")
    except ValueError:
        raise ValueError(MSG_TEMPO) from None
    if minutos < 1:
        raise ValueError(MSG_TEMPO_ZERO)
    return minutos


def tempo_para_campo(minutos: int) -> str:
    """90 -> '1:30' (o formato que ``ler_tempo`` aceita)."""
    return f"{minutos // 60}:{minutos % 60:02d}"


def valor_para_campo(centavos: int) -> str:
    return formatacao.formatar_brl(centavos)


def ler_data(texto: str | None) -> date:
    m = _RE_DATA.match((texto or "").strip())
    if not m:
        raise ValueError(MSG_DATA)
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        raise ValueError(MSG_DATA) from None


def ler_hora(texto: str | None) -> time:
    m = _RE_HORA.match((texto or "").strip())
    if not m:
        raise ValueError(MSG_HORA)
    try:
        return time(int(m.group(1)), int(m.group(2)))
    except ValueError:
        raise ValueError(MSG_HORA) from None


def para_utc(dia: date, hora: time, tz: str) -> datetime:
    """Junta data e hora digitadas no fuso ``tz`` e converte para UTC."""
    return datetime.combine(dia, hora, tzinfo=ZoneInfo(tz)).astimezone(UTC)


def ler_data_hora(texto_data: str | None, texto_hora: str | None, tz: str) -> datetime:
    """Data 'dd/mm/aaaa' + hora 'HH:MM' no fuso ``tz`` -> datetime em UTC."""
    return para_utc(ler_data(texto_data), ler_hora(texto_hora), tz)


def partes_locais(instante: datetime, tz: str) -> tuple[str, str]:
    """Instante (UTC) -> ('dd/mm/aaaa', 'HH:MM') no fuso ``tz``, para preencher campos."""
    local = instante.astimezone(ZoneInfo(tz))
    return (
        f"{local.day:02d}/{local.month:02d}/{local.year:04d}",
        f"{local.hour:02d}:{local.minute:02d}",
    )


def somente_alterados(original: dict, atual: dict) -> dict:
    """Os pares de ``atual`` cujo valor difere do de ``original`` (para editar_os)."""
    return {campo: valor for campo, valor in atual.items() if original.get(campo) != valor}


def previa_diferencas(
    valor_previsto_centavos: int,
    tempo_previsto_minutos: int,
    texto_valor: str | None,
    inicio: tuple[str | None, str | None],
    fim: tuple[str | None, str | None],
    tz: str,
) -> tuple[str | None, str | None]:
    """Prévia (diferença de valor, diferença de tempo) enquanto o usuário digita.

    Cada item é None enquanto as entradas correspondentes não forem válidas. É só uma
    prévia: os números oficiais são calculados pelo serviço na conclusão.
    """
    from osapp.ui import historico

    previa_valor = previa_tempo = None
    try:
        diferenca = ler_valor(texto_valor) - valor_previsto_centavos
        percentual = (
            round(diferenca * 100 / valor_previsto_centavos, 2) if valor_previsto_centavos else None
        )
        previa_valor = historico.texto_diferenca_valor(diferenca, percentual)
    except ValueError:
        pass
    try:
        inicio_utc = ler_data_hora(inicio[0], inicio[1], tz)
        fim_utc = ler_data_hora(fim[0], fim[1], tz)
        if fim_utc > inicio_utc:
            minutos = int((fim_utc - inicio_utc).total_seconds() // 60)
            previa_tempo = historico.texto_diferenca_tempo(minutos - tempo_previsto_minutos)
    except ValueError:
        pass
    return previa_valor, previa_tempo
