"""Frases em português para o histórico da OS. Módulo puro (sem Flet).

Um único mapeamento campo -> (rótulo, formatador) alimenta todas as frases.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from osapp import formatacao
from osapp.services import custos, ordens, status

TEXTO_MAX = 80
SETA = "->"


def _texto(valor: str) -> str:
    valor = " ".join(valor.split())
    return valor if len(valor) <= TEXTO_MAX else valor[: TEXTO_MAX - 1] + "…"


def _dinheiro(valor: str) -> str:
    return formatacao.formatar_brl(int(valor))


def _duracao(valor: str) -> str:
    return formatacao.formatar_duracao(int(valor))


def _data_hora(valor: str) -> str:
    return formatacao.formatar_data_hora(datetime.fromisoformat(valor))


# campo -> (rótulo, formatador do valor guardado como texto)
CAMPOS: dict[str, tuple[str, Callable[[str], str]]] = {
    "status": ("Status", status.rotulo),
    "titulo": ("Título", _texto),
    "descricao": ("Descrição", _texto),
    "valor_previsto_centavos": ("Valor previsto", _dinheiro),
    "tempo_previsto_minutos": ("Tempo previsto", _duracao),
    "filial_id": ("Filial", _texto),
    "valor_realizado_centavos": ("Valor realizado", _dinheiro),
    "inicio_realizado": ("Início", _data_hora),
    "fim_realizado": ("Fim", _data_hora),
    "descricao_realizado": ("Descrição do que foi feito", _texto),
    "equipamento_id": ("Equipamento", _texto),
    "urgencia": ("Urgência", lambda v: _rotulos().nivel(v)),
    "prioridade": ("Prioridade", lambda v: _rotulos().nivel(v)),
    "tipo_id": ("Tipo de manutenção", _texto),
    "origem": ("Origem", lambda v: _rotulos().origem(v)),
    "nota_conclusao": ("Nota para o solicitante", _texto),
    "equipamento_outro": ("Equipamento (outro)", _texto),
}

# Eventos de item de custo: o campo gravado é 'item 12' ou 'item 12 - valor unitário'.
FRASE_ITEM_ADICIONADO = "Item de custo adicionado"
FRASE_ITEM_ALTERADO = "Item de custo alterado"
FRASE_ITEM_REMOVIDO = "Item de custo removido"


def _rotulos():
    from osapp.ui import rotulos

    return rotulos


def _formatar(campo: str | None, valor: str | None) -> str:
    if valor is None:
        return "(vazio)"
    formatador = CAMPOS.get(campo or "", ("", _texto))[1]
    try:
        return formatador(valor)
    except (ValueError, TypeError):
        return _texto(valor)  # valor fora do formato esperado: mostra como está


def _item(valor: str | None) -> str:
    """Texto do item já formatado pelo serviço ('Peças | Rolamento | 2 x R$ 10,00')."""
    return "(vazio)" if valor is None else " ".join(valor.split())


def rotulo_campo(campo: str | None) -> str:
    return CAMPOS[campo][0] if campo in CAMPOS else (campo or "Campo")


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
    rotulo = rotulo_campo(evento.campo)
    novo = _formatar(evento.campo, evento.valor_novo)
    if evento.tipo == ordens.TIPO_REALIZADO:
        return f"{rotulo}: {novo}"
    if evento.tipo in (ordens.TIPO_STATUS, ordens.TIPO_EDICAO):
        return f"{rotulo}: {_formatar(evento.campo, evento.valor_antigo)} {SETA} {novo}"
    return f"{rotulo} alterado"


def comparacao(diferenca: int) -> str:
    """Palavras que acompanham uma diferença (para não depender só de cor)."""
    if diferenca > 0:
        return "Acima do previsto"
    if diferenca < 0:
        return "Abaixo do previsto"
    return "Igual ao previsto"


def _com_sinal(texto: str, diferenca: int) -> str:
    return f"+{texto}" if diferenca > 0 else texto


def texto_diferenca_valor(diferenca_centavos: int, percentual: float | None) -> str:
    """Ex.: '+R$ 20,00 (+20,0%) - Acima do previsto'. Sem percentual se o previsto era 0."""
    partes = _com_sinal(formatacao.formatar_brl(diferenca_centavos), diferenca_centavos)
    if percentual is not None:
        partes += f" ({percentual:+.1f}%)".replace(".", ",") if diferenca_centavos else " (0,0%)"
    return f"{partes} - {comparacao(diferenca_centavos)}"


def texto_diferenca_tempo(diferenca_minutos: int) -> str:
    """Ex.: '+0h30 - Acima do previsto' ou '-0h15 - Abaixo do previsto'."""
    duracao = formatacao.formatar_duracao(abs(diferenca_minutos))
    sinal = "+" if diferenca_minutos > 0 else "-" if diferenca_minutos < 0 else ""
    return f"{sinal}{duracao} - {comparacao(diferenca_minutos)}"
