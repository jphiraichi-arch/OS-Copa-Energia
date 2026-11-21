"""Leitura e formatação dos campos de dinheiro, duração e hora. Módulo puro.

Desde 21/11/2026 não há máscara ao vivo: o campo nunca é reescrito enquanto o usuário
digita (em 4G lento a reescrita perdia dígitos). O texto é lido e formatado quando o
campo perde o foco (``texto``) e validado ao gravar (``valor``/``erro``).

Regras:
- Dinheiro: as de ``formatacao.ler_brl``: '150' = R$ 150,00; '150,50' e '1.234,56'
  aceitos; '150.50' e '150,5' recusados (o ponto só separa milhares; centavos com 2
  dígitos). 'R$' é ignorado. Vazio = 0.
- Duração e hora: 'H:MM' (ou 'HH:MM'); só dígitos também vale, porque o teclado
  numérico do celular nem sempre tem ':': 1 ou 2 dígitos são horas inteiras ('2' =
  2:00, '14' = 14:00); com 3 ou mais, os dois últimos são os minutos ('130' = 1:30,
  '0930' = 09:30). Duração vazia = 0:00 (não informado); hora vazia é erro.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import time

from osapp import formatacao

VALOR_MAX_CENTAVOS = 9_999_999_999  # R$ 99.999.999,99 (o limite do serviço)
HORAS_MAX_DURACAO = 999

MSG_DINHEIRO = "Valor inválido. Use o formato 1.234,56."
MSG_DINHEIRO_MAX = "Use no máximo R$ 99.999.999,99."
MSG_DURACAO = "Duração inválida. Use H:MM, por exemplo 1:30."
MSG_MINUTOS = "Minutos devem ficar entre 00 e 59."
MSG_DURACAO_MAX = "Use no máximo 999 horas."
MSG_HORA = "Hora inválida. Use HH:MM, por exemplo 13:50."
MSG_HORA_VAZIA = "Informe a hora."

_RE_HORA_MINUTO = re.compile(r"^(\d{1,4}):(\d{2})$")
_RE_DIGITOS = re.compile(r"^\d{1,5}$")


@dataclass(frozen=True)
class Lido:
    valor: object  # centavos (int), minutos (int) ou datetime.time; None se houver erro
    texto: str  # o texto formatado (quando há erro, o texto recebido, sem mudança)
    erro: str | None = None


def _limpo(texto: object) -> str:
    return str(texto or "").replace(" ", " ").strip()


# --- Dinheiro ---------------------------------------------------------------------------


def texto_dinheiro(centavos: int) -> str:
    """Texto do campo (o 'R$' é o prefixo do campo): 15000 -> '150,00'; 0 -> ''."""
    return formatacao.formatar_brl(centavos).removeprefix("R$ ") if centavos else ""


def ler_dinheiro(texto: object) -> Lido:
    bruto = _limpo(texto)
    sem_moeda = bruto.removeprefix("R$").strip()
    if not sem_moeda:
        return Lido(0, "")
    try:
        centavos = formatacao.ler_brl(sem_moeda)
    except ValueError:
        return Lido(None, bruto, MSG_DINHEIRO)
    if centavos > VALOR_MAX_CENTAVOS:
        return Lido(None, bruto, MSG_DINHEIRO_MAX)
    return Lido(centavos, texto_dinheiro(centavos))


# --- Duração e hora -------------------------------------------------------------------


def _horas_minutos(bruto: str) -> tuple[int, int] | None:
    m = _RE_HORA_MINUTO.match(bruto)
    if m:
        return int(m.group(1)), int(m.group(2))
    if _RE_DIGITOS.match(bruto):
        if len(bruto) <= 2:
            return int(bruto), 0
        return divmod(int(bruto), 100)
    return None


def texto_duracao(minutos: int) -> str:
    """90 -> '1:30'; 0 -> '' (não informado)."""
    if not minutos:
        return ""
    horas, resto = divmod(minutos, 60)
    return f"{horas}:{resto:02d}"


def ler_duracao(texto: object) -> Lido:
    bruto = _limpo(texto)
    if not bruto:
        return Lido(0, "")
    partes = _horas_minutos(bruto)
    if partes is None:
        return Lido(None, bruto, MSG_DURACAO)
    horas, minutos = partes
    if minutos > 59:
        return Lido(None, bruto, MSG_MINUTOS)
    if horas > HORAS_MAX_DURACAO:
        return Lido(None, bruto, MSG_DURACAO_MAX)
    total = horas * 60 + minutos
    return Lido(total, texto_duracao(total) or "0:00")


def texto_hora(valor: time | None) -> str:
    return f"{valor.hour:02d}:{valor.minute:02d}" if valor is not None else ""


def ler_hora(texto: object) -> Lido:
    bruto = _limpo(texto)
    if not bruto:
        return Lido(None, "", MSG_HORA_VAZIA)
    partes = _horas_minutos(bruto)
    if partes is None:
        return Lido(None, bruto, MSG_HORA)
    horas, minutos = partes
    if minutos > 59:
        return Lido(None, bruto, MSG_MINUTOS)
    if horas > 23:
        return Lido(None, bruto, MSG_HORA)
    valor = time(horas, minutos)
    return Lido(valor, texto_hora(valor))
