"""Máscaras de digitação "de caixa registradora" para dinheiro e hora. Módulo puro.

O usuário digita só números; cada dígito novo entra pela direita e empurra os outros.
Nunca se digita vírgula nem dois-pontos. Textos colados mantêm só os dígitos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from osapp import formatacao

DIGITOS_MAX_DINHEIRO = 10  # 99.999.999,99 (o limite do serviço)
DIGITOS_MAX_DURACAO = 5  # 999:59
DIGITOS_MAX_RELOGIO = 4  # 23:59
HORAS_MAX_DURACAO = 999

DURACAO = "duracao"
RELOGIO = "relogio"

MSG_MINUTOS = "Minutos devem ficar entre 00 e 59."
MSG_HORA = "Hora inválida."
MSG_DURACAO_MAX = "Use no máximo 999 horas."


@dataclass(frozen=True)
class Mascarado:
    texto: str  # o que o campo mostra
    digitos: str  # os dígitos significativos guardados
    valor: object  # centavos (int), minutos (int) ou datetime.time; None se houver erro
    erro: str | None = None  # mensagem para mostrar sob o campo; não impede a digitação


def so_digitos(texto: object, maximo: int) -> str:
    """Só os dígitos, sem zeros à esquerda, no máximo ``maximo`` (os excedentes são ignorados)."""
    digitos = "".join(c for c in str(texto or "") if c.isdigit()).lstrip("0")
    return digitos[:maximo]


def mascara_dinheiro(texto: object) -> Mascarado:
    """'219' -> '2,19'; '1000' -> '10,00'; '123456' -> '1.234,56'. Valor em centavos."""
    digitos = so_digitos(texto, DIGITOS_MAX_DINHEIRO)
    centavos = int(digitos or 0)
    return Mascarado(formatacao.formatar_brl(centavos).removeprefix("R$ "), digitos, centavos)


def mascara_hora(texto: object, tipo: str = DURACAO) -> Mascarado:
    """Duração: '130' -> '1:30' (minutos). Relógio: '1350' -> '13:50' (datetime.time).

    Os dois últimos dígitos são os minutos. Minutos de 60 a 99, hora de relógio de 24
    para cima ou duração acima de 999 h geram ``erro`` (a digitação continua livre).
    """
    maximo = DIGITOS_MAX_RELOGIO if tipo == RELOGIO else DIGITOS_MAX_DURACAO
    digitos = so_digitos(texto, maximo)
    numero = int(digitos or 0)
    horas, minutos = divmod(numero, 100)
    if tipo == RELOGIO:
        exibicao = f"{horas:02d}:{minutos:02d}"
    else:
        exibicao = f"{horas}:{minutos:02d}"
    erro = None
    if minutos > 59:
        erro = MSG_MINUTOS
    elif tipo == RELOGIO and horas > 23:
        erro = MSG_HORA
    elif tipo != RELOGIO and horas > HORAS_MAX_DURACAO:
        erro = MSG_DURACAO_MAX
    if erro:
        valor = None
    elif tipo == RELOGIO:
        valor = time(horas, minutos)
    else:
        valor = horas * 60 + minutos
    return Mascarado(exibicao, digitos, valor, erro)


def editar_digitos(digitos: str, texto_antigo: str, texto_novo: str, maximo: int) -> str:
    """Novos dígitos guardados a partir da edição feita no campo, onde quer que esteja o cursor.

    Compara o texto antigo com o novo (prefixo e sufixo comuns): os dígitos inseridos
    entram sempre pela direita; cada dígito apagado tira o último dígito guardado (apagar
    só um separador também tira um). Se a edição substituiu o texto todo (selecionar tudo
    e colar ou digitar), ficam só os dígitos inseridos.
    """
    antigo, novo = texto_antigo or "", texto_novo or ""
    inicio = 0
    while inicio < min(len(antigo), len(novo)) and antigo[inicio] == novo[inicio]:
        inicio += 1
    fim = 0
    while (
        fim < min(len(antigo), len(novo)) - inicio
        and antigo[len(antigo) - 1 - fim] == novo[len(novo) - 1 - fim]
    ):
        fim += 1
    removido = antigo[inicio : len(antigo) - fim]
    inserido = "".join(c for c in novo[inicio : len(novo) - fim] if c.isdigit())
    if removido and len(removido) == len(antigo):
        return so_digitos(inserido, maximo)
    if removido:
        apagar = max(1, sum(c.isdigit() for c in removido))
        digitos = digitos[: max(0, len(digitos) - apagar)]
    return so_digitos(digitos + inserido, maximo)


def digitos_de_centavos(centavos: int) -> str:
    return str(centavos) if centavos else ""


def digitos_de_minutos(minutos: int) -> str:
    """90 minutos -> '130' (os dígitos que o campo de duração mostraria como 1:30)."""
    horas, resto = divmod(minutos, 60)
    return str(horas * 100 + resto) if minutos else ""


def digitos_de_hora(valor: time) -> str:
    return str(valor.hour * 100 + valor.minute) if (valor.hour or valor.minute) else ""
