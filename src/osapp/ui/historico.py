"""Frases em português para o histórico da OS. Módulo puro (sem Flet).

Os rótulos e a formatação dos valores vêm de ui/rotulos_eventos.py (prompt 26).
"""

from __future__ import annotations

from osapp import formatacao
from osapp.services import custos, ordens, visualizacoes
from osapp.ui import rotulos_eventos

SETA = "->"
VAZIO = rotulos_eventos.VAZIO
# Rótulos e formatadores: ui/rotulos_eventos.py (um só mapeamento para todo o app).
CAMPOS = rotulos_eventos.CAMPOS
_texto = rotulos_eventos._texto


# Eventos de item de custo: o campo gravado é 'item 12' ou 'item 12 - valor unitário'.
FRASE_ITEM_ADICIONADO = "Item de custo adicionado"
FRASE_ITEM_ALTERADO = "Item de custo alterado"
FRASE_ITEM_REMOVIDO = "Item de custo removido"
FRASE_EXCLUSAO = "Ordem de Serviço excluída (enviada para a Lixeira)"
FRASE_RESTAURACAO = "Ordem de Serviço restaurada da Lixeira"


def _formatar(campo: str | None, valor: str | None) -> str:
    return rotulos_eventos.formatar(campo, valor)


def _item(valor: str | None) -> str:
    """Texto do item já formatado pelo serviço ('Peças | Rolamento | 2 x R$ 10,00')."""
    return VAZIO if valor is None else " ".join(valor.split())


def rotulo_campo(campo: str | None) -> str:
    return rotulos_eventos.rotulo(campo)


def frase(evento) -> str:
    """Frase de um evento (``EventoDTO``), por exemplo 'Status: Aberta -> Em execução'."""
    if evento.tipo == ordens.TIPO_CRIACAO:
        return "Ordem de Serviço criada"
    if evento.tipo == custos.TIPO_ITEM_ADICIONADO:
        return f"{FRASE_ITEM_ADICIONADO}: {_item(evento.valor_novo)}"
    if evento.tipo == custos.TIPO_ITEM_REMOVIDO:
        return f"{FRASE_ITEM_REMOVIDO}: {_item(evento.valor_antigo)}"
    if evento.tipo == custos.TIPO_ITEM_ALTERADO:
        _item_gravado, _sep, campo_do_item = (evento.campo or "").partition(" - ")
        detalhe = f" ({campo_do_item})" if campo_do_item else ""
        return (
            f"{FRASE_ITEM_ALTERADO}{detalhe}: {_item(evento.valor_antigo)} {SETA} "
            f"{_item(evento.valor_novo)}"
        )
    if evento.tipo == visualizacoes.TIPO_VISUALIZACAO:  # prompt 42
        return f"Visualizada por {_texto(evento.valor_novo or '')}"
    if evento.tipo == ordens.TIPO_EXCLUSAO:
        return f"{FRASE_EXCLUSAO}. Motivo: {_texto(evento.valor_novo or '')}"
    if evento.tipo == ordens.TIPO_RESTAURACAO:
        return f"{FRASE_RESTAURACAO}. Motivo da exclusão: {_texto(evento.valor_antigo or '')}"
    rotulo = rotulo_campo(evento.campo)
    novo = _formatar(evento.campo, evento.valor_novo)
    observacao = getattr(evento, "observacao", None)
    if observacao and evento.tipo in (ordens.TIPO_EDICAO, ordens.TIPO_STATUS):  # p. 41: motivo
        return (
            f"{rotulo}: {_formatar(evento.campo, evento.valor_antigo)} {SETA} {novo} ({observacao})"
        )
    if evento.tipo == ordens.TIPO_REALIZADO:
        return f"{rotulo}: {novo}"
    # STATUS, EDICAO e qualquer tipo desconhecido: 'Rótulo: antigo -> novo'.
    return f"{rotulo}: {_formatar(evento.campo, evento.valor_antigo)} {SETA} {novo}"


IGUAL = "Igual ao previsto"
NAO_PREVISTO = "(não previsto)"
SEM_GASTO = "sem gasto"
ACIMA = "acima do previsto"
ABAIXO = "abaixo do previsto"


def comparacao(diferenca: int) -> str:
    """Palavras que acompanham uma diferença (para não depender só de cor)."""
    if diferenca > 0:
        return "Acima do previsto"
    if diferenca < 0:
        return "Abaixo do previsto"
    return IGUAL


def texto_diferenca_valor(diferenca_centavos: int, percentual: float | None) -> str:
    """Diferença de dinheiro em palavras (Detalhe, relatório, prévia da conclusão).

    'R$ 120,00 acima do previsto (+12%)'; 'R$ 120,00 abaixo do previsto (\u221212%)';
    'Igual ao previsto'. O percentual leva o sinal; o valor, não.
    Prompt 31 — previsto 0 (o percentual chega como None, nunca há divisão por zero):
    realizado > 0 -> '+R$ 150,00 (não previsto)'; realizado 0 -> 'R$ 0,00 — sem gasto'.
    """
    if percentual is None:
        return _sem_previsto(diferenca_centavos)
    if diferenca_centavos == 0:
        return IGUAL
    valor = formatacao.formatar_brl(abs(diferenca_centavos))
    palavras = ACIMA if diferenca_centavos > 0 else ABAIXO
    return f"{valor} {palavras} ({formatacao.formatar_percentual(percentual, sinal=True)})"


def _sem_previsto(diferenca_centavos: int) -> str:
    """Previsto 0: a diferença é o próprio realizado (nunca negativa)."""
    if diferenca_centavos == 0:
        return f"{formatacao.formatar_brl(0)} — {SEM_GASTO}"
    return f"+{formatacao.formatar_brl(abs(diferenca_centavos))} {NAO_PREVISTO}"


def texto_diferenca_compacta(diferenca_centavos: int, percentual: float | None) -> str:
    """Linhas de categoria da tabela de custos: só valor e percentual, sem palavras.

    '+R$ 120,00 (+12%)'; '\u2212R$ 120,00 (\u221212%)'; 'R$ 0,00'.
    Previsto 0 (percentual None): as mesmas frases de texto_diferenca_valor.
    """
    if percentual is None:
        return _sem_previsto(diferenca_centavos)
    valor = valor_com_sinal(diferenca_centavos)
    if diferenca_centavos == 0:
        return valor
    return f"{valor} ({formatacao.formatar_percentual(percentual, sinal=True)})"


def valor_com_sinal(diferenca_centavos: int) -> str:
    """'+R$ 120,00', '\u2212R$ 120,00' ou 'R$ 0,00' (só nas linhas de categoria)."""
    valor = formatacao.formatar_brl(abs(diferenca_centavos))
    if diferenca_centavos > 0:
        return f"+{valor}"
    if diferenca_centavos < 0:
        return f"{formatacao.MENOS}{valor}"
    return valor


def etiqueta_diferenca(diferenca: int) -> str | None:
    """Etiqueta curta ao lado do valor da categoria: 'acima', 'abaixo' ou nada."""
    if diferenca > 0:
        return "acima"
    if diferenca < 0:
        return "abaixo"
    return None


def texto_diferenca_tempo(diferenca_minutos: int) -> str:
    """'2h58 abaixo do previsto', '2h58 acima do previsto' ou 'Igual ao previsto'.

    Nunca um sinal de menos junto com as palavras."""
    if diferenca_minutos == 0:
        return IGUAL
    duracao = formatacao.formatar_duracao(abs(diferenca_minutos))
    return f"{duracao} {ACIMA if diferenca_minutos > 0 else ABAIXO}"
