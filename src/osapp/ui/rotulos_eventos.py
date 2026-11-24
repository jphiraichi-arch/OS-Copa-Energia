"""Rótulos e formatação dos campos de os_eventos (prompt 26). Módulo puro, sem Flet.

Todo ``campo`` que o app já gravou no histórico tem um rótulo em português, inclusive os
de campos que saíram (marcados '(legado)'). Os valores são formatados pelo tipo:
centavos -> R$, minutos -> 1h30, instantes -> dd/mm/aaaa HH:MM em OS_TZ, códigos de
status, urgência, prioridade e origem -> rótulos, booleanos -> Sim/Não, vazio -> '—'.
Um campo desconhecido aparece como 'Campo alterado' (o nome cru nunca chega à tela) e
deixa um aviso no log do servidor. A lista de campos sem rótulo no banco sai do comando
`python -m osapp.cli verificar-rotulos-eventos`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import datetime

from osapp import formatacao
from osapp.services import status

logger = logging.getLogger(__name__)

VAZIO = "—"
TEXTO_MAX = 80
CAMPO_DESCONHECIDO = "Campo alterado"
ROTULO_ITEM = "Item de custo"
# Eventos de item: 'item 12' ou 'item 12 - valor unitário'.
RE_CAMPO_DE_ITEM = re.compile(r"^item \d+( - .+)?$")


def _texto(valor: str) -> str:
    valor = " ".join(valor.split())
    return valor if len(valor) <= TEXTO_MAX else valor[: TEXTO_MAX - 1] + "…"


def _centavos(valor: str) -> str:
    return formatacao.formatar_brl(int(valor))


def _minutos(valor: str) -> str:
    return formatacao.formatar_duracao(int(valor))


def _instante(valor: str) -> str:
    return formatacao.formatar_data_hora(datetime.fromisoformat(valor))


def _nivel(valor: str) -> str:
    from osapp.ui import rotulos

    return rotulos.nivel(valor)


def _origem(valor: str) -> str:
    from osapp.ui import rotulos

    return rotulos.origem(valor)


def _booleano(valor: str) -> str:
    return "Sim" if valor.strip().lower() in ("true", "1", "sim") else "Não"


def _equipamento_legado(valor: str) -> str:
    return f"Equipamento nº {int(valor)} (legado)"


def _id_legado(valor: str) -> str:
    return f"nº {int(valor)}"


# campo -> (rótulo, formatador do valor guardado como texto)
CAMPOS: dict[str, tuple[str, Callable[[str], str]]] = {
    # Atuais
    "status": ("Status", status.rotulo),
    "titulo": ("Título", _texto),
    "descricao": ("Descrição", _texto),
    "tempo_previsto_minutos": ("Tempo previsto", _minutos),
    "filial_id": ("Filial", _texto),  # gravado como o código da filial
    "tipo_id": ("Tipo de manutenção", _texto),  # gravado como o nome do tipo
    "urgencia": ("Urgência", _nivel),
    "prioridade": ("Prioridade", _nivel),
    "origem": ("Origem", _origem),
    "inicio_realizado": ("Início", _instante),
    "fim_realizado": ("Fim", _instante),
    "descricao_realizado": ("Descrição do que foi feito", _texto),
    "nota_conclusao": ("Nota para o solicitante", _texto),
    "numero_sap": ("Nº SAP", _texto),
    "exclusao": ("Exclusão", _texto),
    "sem_gasto_previsto": ("Sem gasto (previsto)", _booleano),  # prompt 31
    "sem_gasto_realizado": (
        "Sem gasto (realizado)",
        _booleano,
    ),  # EXCLUSAO e RESTAURACAO (prompt 24): o motivo
    # Campos que saíram do modelo (eventos antigos continuam legíveis)
    "valor_previsto_centavos": ("Valor previsto (legado)", _centavos),
    "valor_realizado_centavos": ("Valor realizado (legado)", _centavos),
    "equipamento_id": ("Equipamento (legado)", _equipamento_legado),
    "equipamento_outro": ("Equipamento (legado)", _texto),
    "executor_id": ("Executor (legado)", _id_legado),
    "iniciado_em": ("Início da execução (legado)", _instante),
    "concluido_em": ("Conclusão (legado)", _instante),
}


def tem_rotulo(campo: str | None) -> bool:
    return campo is None or campo in CAMPOS or bool(RE_CAMPO_DE_ITEM.match(campo))


def rotulo(campo: str | None) -> str:
    """Rótulo em português; campo desconhecido -> 'Campo alterado' (e aviso no log)."""
    if campo in CAMPOS:
        return CAMPOS[campo][0]
    if campo is not None and RE_CAMPO_DE_ITEM.match(campo):
        return ROTULO_ITEM
    logger.warning("Campo de evento sem rótulo: %r.", campo)
    return CAMPO_DESCONHECIDO


def formatar(campo: str | None, valor: str | None) -> str:
    """Valor guardado (texto) formatado pelo tipo do campo; vazio -> '—'."""
    if valor is None or valor == "":
        return VAZIO
    formatador = CAMPOS.get(campo or "", ("", _texto))[1]
    try:
        return formatador(valor)
    except (ValueError, TypeError):
        return _texto(valor)  # fora do formato esperado: mostra o texto como está
