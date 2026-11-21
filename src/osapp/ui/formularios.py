"""Conversão entre o que o usuário digita e os argumentos dos serviços. Módulo puro.

É só conveniência: a validação que vale é sempre a do serviço.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from osapp import formatacao
from osapp.services import custos
from osapp.services.erros import ErroValidacao

MSG_DATA = "Data inválida. Use o formato dd/mm/aaaa."
MSG_HORA = "Hora inválida. Use o formato HH:MM, por exemplo 13:50."
MSG_QUANTIDADE = "Quantidade inválida. Use o formato 1 ou 1,5."
MSG_CATEGORIA = "Escolha a categoria."

_RE_DATA = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_RE_HORA = re.compile(r"^(\d{1,2}):(\d{2})$")


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


def ler_quantidade(texto: str | None) -> Decimal:
    """'1', '1,5' ou '1,50' -> Decimal com 2 casas. ValueError com mensagem em português."""
    try:
        return formatacao.ler_quantidade(texto or "")
    except ValueError:
        raise ValueError(MSG_QUANTIDADE) from None


def quantidade_para_campo(quantidade: Decimal) -> str:
    return formatacao.formatar_quantidade(quantidade)


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


# --- Itens de custo ---------------------------------------------------------------------


@dataclass(frozen=True)
class ItemLocal:
    """Item como a tela o guarda. Tem os campos que ``custos.calcular_resumo`` lê.

    ``id`` é o id gravado (None para um item que só existe na tela). ``chave`` identifica
    o item na tela, gravado ou não.
    """

    chave: int
    id: int | None
    fase: str
    categoria_id: int
    categoria_nome: str
    categoria_ordem: int
    descricao: str
    quantidade: Decimal
    valor_unitario_centavos: int

    @property
    def total_centavos(self) -> int:
        return custos.total_da_linha(self.quantidade, self.valor_unitario_centavos)


def item_local(dto, chave: int | None = None) -> ItemLocal:
    """``custos.ItemDTO`` -> ItemLocal (a chave é o id gravado)."""
    return ItemLocal(
        chave=dto.id if chave is None else chave,
        id=dto.id,
        fase=dto.fase,
        categoria_id=dto.categoria_id,
        categoria_nome=dto.categoria_nome,
        categoria_ordem=dto.categoria_ordem,
        descricao=dto.descricao,
        quantidade=dto.quantidade,
        valor_unitario_centavos=dto.valor_unitario_centavos,
    )


def itens_da_fase(itens, fase: str) -> list[ItemLocal]:
    return [item_local(i) for i in itens if i.fase == fase]


def para_entrada(itens: list[ItemLocal]) -> list[custos.ItemEntrada]:
    """Itens da tela -> argumento ``itens_previstos``/``itens_realizados`` dos serviços."""
    return [
        custos.ItemEntrada(
            categoria_id=i.categoria_id,
            descricao=i.descricao,
            quantidade=i.quantidade,
            valor_unitario_centavos=i.valor_unitario_centavos,
        )
        for i in itens
    ]


def copiar_itens(itens: list[ItemLocal], fase: str, primeira_chave: int) -> list[ItemLocal]:
    """Cópias não gravadas dos itens, na fase ``fase`` ('Copiar itens previstos')."""
    return [
        replace(item, chave=primeira_chave + n, id=None, fase=fase) for n, item in enumerate(itens)
    ]


def ler_item(
    categorias, fase: str, chave: int, item_id: int | None, valores: dict
) -> tuple[ItemLocal | None, dict[str, str]]:
    """Valores digitados no diálogo do item -> (ItemLocal, {}) ou (None, {campo: mensagem}).

    ``valores``: categoria_id (int ou None), descricao (str), quantidade (texto),
    valor_unitario_centavos (int ou None quando a máscara indica erro). Usa os validadores
    puros do serviço; o serviço valida de novo ao gravar.
    """
    erros: dict[str, str] = {}
    categoria = next((c for c in categorias if c.id == valores.get("categoria_id")), None)
    if categoria is None:
        erros["categoria_id"] = MSG_CATEGORIA
    descricao = quantidade = valor = None
    try:
        descricao = custos.validar_descricao(valores.get("descricao"))
    except ErroValidacao as exc:
        erros["descricao"] = exc.mensagem
    try:
        quantidade = custos.validar_quantidade(ler_quantidade(valores.get("quantidade")))
    except ValueError as exc:
        erros["quantidade"] = str(exc)
    except ErroValidacao as exc:
        erros["quantidade"] = exc.mensagem
    try:
        valor = custos.validar_valor_unitario(valores.get("valor_unitario_centavos"))
    except ErroValidacao as exc:
        erros["valor_unitario_centavos"] = exc.mensagem
    if erros:
        return None, erros
    return (
        ItemLocal(
            chave=chave,
            id=item_id,
            fase=fase,
            categoria_id=categoria.id,
            categoria_nome=categoria.nome,
            categoria_ordem=categoria.ordem,
            descricao=descricao,
            quantidade=quantidade,
            valor_unitario_centavos=valor,
        ),
        {},
    )


def alteracoes_do_item(antes: ItemLocal, depois: ItemLocal) -> dict:
    """Só os campos do item que mudaram (argumento ``alteracoes`` de ``editar_item``)."""
    return {
        campo: getattr(depois, campo)
        for campo in custos.CAMPOS_DO_ITEM
        if getattr(antes, campo) != getattr(depois, campo)
    }


def resumo_previa(itens: list[ItemLocal]) -> custos.ResumoCustos:
    """Prévia dos totais (o número oficial é o ``resumo_custos`` devolvido pelo serviço)."""
    return custos.calcular_resumo(itens)


# --- Conclusão --------------------------------------------------------------------------


def instante(texto_data: str | None, hora: time | None, tz: str) -> datetime:
    """Data 'dd/mm/aaaa' + hora do CampoHora no fuso ``tz`` -> UTC. ValueError se inválido."""
    if hora is None:
        raise ValueError(MSG_HORA)
    return para_utc(ler_data(texto_data), hora, tz)


def previa_tempo(
    tempo_previsto_minutos: int,
    inicio: tuple[str | None, time | None],
    fim: tuple[str | None, time | None],
    tz: str,
) -> str | None:
    """Diferença de tempo enquanto o usuário digita; None enquanto não for válida."""
    from osapp.ui import historico

    try:
        inicio_utc = instante(inicio[0], inicio[1], tz)
        fim_utc = instante(fim[0], fim[1], tz)
    except ValueError:
        return None
    if fim_utc <= inicio_utc:
        return None
    minutos = int((fim_utc - inicio_utc).total_seconds() // 60)
    return historico.texto_diferenca_tempo(minutos - tempo_previsto_minutos)
