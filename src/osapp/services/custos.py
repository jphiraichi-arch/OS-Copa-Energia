"""Itens de custo das Ordens de Serviço.

Cada OS tem itens em duas fases, PREVISTO e REALIZADO. Totais nunca são gravados nem
recebidos: são calculados aqui, com ``decimal.Decimal`` (nada de float).

Este módulo tem duas partes:
- funções puras (``total_da_linha``, ``calcular_resumo``, validação), sem banco, que as
  telas podem reusar nas prévias;
- operações de escrita (``adicionar_item``, ``editar_item``, ``remover_item``), com as
  mesmas regras de permissão, filial, versão e histórico do resto do serviço de OS.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from osapp import formatacao
from osapp.busca import normalizar_busca
from osapp.db import sessao
from osapp.models import OsItemCusto
from osapp.models.custos import FASE_PREVISTO, FASE_REALIZADO
from osapp.repositories import CategoriaCustoRepo, OrdemServicoRepo
from osapp.services.auth import carregar_ator
from osapp.services.erros import ErroPermissao, ErroValidacao
from osapp.services.permissoes import pode_acessar_filial

logger = logging.getLogger(__name__)

FASES = (FASE_PREVISTO, FASE_REALIZADO)
DESCRICAO_ITEM_MAX = 200
QUANTIDADE_MIN = Decimal("0.01")
QUANTIDADE_MAX = Decimal("99999.99")
VALOR_UNITARIO_MAX = 9_999_999_999
ITENS_MAX_POR_FASE = 100
SUGESTOES_PADRAO = 8
SUGESTOES_MAX = 20
SUGESTAO_TERMO_MIN = 2  # caracteres (já normalizados)

TIPO_ITEM_ADICIONADO = "ITEM_ADICIONADO"
TIPO_ITEM_ALTERADO = "ITEM_ALTERADO"
TIPO_ITEM_REMOVIDO = "ITEM_REMOVIDO"

CAMPOS_DO_ITEM = {
    "categoria_id": "categoria",
    "descricao": "descrição",
    "quantidade": "quantidade",
    "valor_unitario_centavos": "valor unitário",
}


# --- DTOs ------------------------------------------------------------------------------


@dataclass(frozen=True)
class CategoriaDTO:
    id: int
    codigo: str
    nome: str
    ordem: int


@dataclass(frozen=True)
class ItemEntrada:
    """Um item como chega aos serviços (criação da OS, conclusão ou inclusão avulsa)."""

    categoria_id: int
    descricao: str
    quantidade: Decimal
    valor_unitario_centavos: int


@dataclass(frozen=True)
class ItemDTO:
    id: int
    fase: str
    categoria_id: int
    categoria_codigo: str
    categoria_nome: str
    categoria_ordem: int
    descricao: str
    quantidade: Decimal
    valor_unitario_centavos: int
    total_centavos: int


@dataclass(frozen=True)
class ResumoCategoria:
    categoria_id: int
    categoria_nome: str
    previsto_centavos: int
    realizado_centavos: int
    diferenca_centavos: int  # realizado - previsto
    diferenca_percentual: float | None  # None quando o previsto da categoria é 0


@dataclass(frozen=True)
class ResumoCustos:
    por_categoria: tuple[ResumoCategoria, ...]  # na ordem das categorias
    total_previsto_centavos: int
    total_realizado_centavos: int
    diferenca_centavos: int
    diferenca_percentual: float | None  # None quando o previsto total é 0


# --- Cálculo (puro) --------------------------------------------------------------------


def total_da_linha(quantidade: Decimal, valor_unitario_centavos: int) -> int:
    """quantidade x valor unitário, arredondado a centavos com ROUND_HALF_UP."""
    exato = Decimal(valor_unitario_centavos) * Decimal(quantidade)
    return int(exato.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def percentual(diferenca: int, base: int) -> float | None:
    """Diferença em % da base, com 2 casas (ROUND_HALF_UP); None quando a base é 0."""
    if base == 0:
        return None
    return float(
        (Decimal(diferenca) * 100 / Decimal(base)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    )


def calcular_resumo(itens: Iterable) -> ResumoCustos:
    """Totais por categoria e gerais de cada fase, e a diferença realizado - previsto.

    Função pura (sem banco). Cada item precisa de: fase, categoria_id, categoria_nome,
    categoria_ordem, quantidade e valor_unitario_centavos (como ``ItemDTO``).
    """
    por_categoria: dict[int, dict] = {}
    for item in itens:
        dados = por_categoria.setdefault(
            item.categoria_id,
            {
                "nome": item.categoria_nome,
                "ordem": item.categoria_ordem,
                FASE_PREVISTO: 0,
                FASE_REALIZADO: 0,
            },
        )
        dados[item.fase] += total_da_linha(item.quantidade, item.valor_unitario_centavos)
    linhas = []
    for categoria_id, dados in sorted(por_categoria.items(), key=lambda i: (i[1]["ordem"], i[0])):
        previsto, realizado = dados[FASE_PREVISTO], dados[FASE_REALIZADO]
        linhas.append(
            ResumoCategoria(
                categoria_id=categoria_id,
                categoria_nome=dados["nome"],
                previsto_centavos=previsto,
                realizado_centavos=realizado,
                diferenca_centavos=realizado - previsto,
                diferenca_percentual=percentual(realizado - previsto, previsto),
            )
        )
    total_previsto = sum(linha.previsto_centavos for linha in linhas)
    total_realizado = sum(linha.realizado_centavos for linha in linhas)
    return ResumoCustos(
        por_categoria=tuple(linhas),
        total_previsto_centavos=total_previsto,
        total_realizado_centavos=total_realizado,
        diferenca_centavos=total_realizado - total_previsto,
        diferenca_percentual=percentual(total_realizado - total_previsto, total_previsto),
    )


# --- Validação (pura) ------------------------------------------------------------------


def _e_int(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def validar_descricao(valor: object) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ErroValidacao("descricao", "Informe a descrição do item.")
    valor = valor.strip()
    if len(valor) > DESCRICAO_ITEM_MAX:
        raise ErroValidacao(
            "descricao", f"A descrição do item deve ter no máximo {DESCRICAO_ITEM_MAX} caracteres."
        )
    return valor


def validar_quantidade(valor: object) -> Decimal:
    if isinstance(valor, bool) or not isinstance(valor, Decimal | int):
        raise ErroValidacao("quantidade", "Informe uma quantidade válida.")
    valor = Decimal(valor)
    if not valor.is_finite() or valor != valor.quantize(Decimal("0.01")):
        raise ErroValidacao("quantidade", "A quantidade aceita no máximo 2 casas decimais.")
    if not QUANTIDADE_MIN <= valor <= QUANTIDADE_MAX:
        raise ErroValidacao("quantidade", "A quantidade deve ficar entre 0,01 e 99.999,99.")
    return valor.quantize(Decimal("0.01"))


def validar_valor_unitario(valor: object) -> int:
    if not _e_int(valor):
        raise ErroValidacao("valor_unitario_centavos", "Informe um valor válido.")
    if valor < 0:
        raise ErroValidacao("valor_unitario_centavos", "O valor não pode ser negativo.")
    if valor > VALOR_UNITARIO_MAX:
        raise ErroValidacao("valor_unitario_centavos", "O valor é maior que o máximo permitido.")
    return valor


def validar_fase(valor: object) -> str:
    if valor not in FASES:
        raise ErroValidacao("fase", "Fase inválida.")
    return valor


def categoria_ativa(s, categoria_id: object):
    categoria = CategoriaCustoRepo(s).obter(categoria_id) if _e_int(categoria_id) else None
    if categoria is None or not categoria.ativo:
        raise ErroValidacao("categoria_id", "Escolha uma categoria válida.")
    return categoria


def validar_itens_de_entrada(s, itens: object, campo: str) -> list[tuple]:
    """Valida uma lista de ``ItemEntrada`` (pelo menos 1, no máximo 100).

    Devolve tuplas (categoria, descrição, quantidade, valor unitário) já normalizadas.
    """
    if not isinstance(itens, list | tuple) or not itens:
        raise ErroValidacao(campo, "Inclua pelo menos um item de custo.")
    if len(itens) > ITENS_MAX_POR_FASE:
        raise ErroValidacao(campo, f"No máximo {ITENS_MAX_POR_FASE} itens por fase.")
    normalizados = []
    for item in itens:
        if not isinstance(item, ItemEntrada):
            raise ErroValidacao(campo, "Item de custo inválido.")
        normalizados.append(
            (
                categoria_ativa(s, item.categoria_id),
                validar_descricao(item.descricao),
                validar_quantidade(item.quantidade),
                validar_valor_unitario(item.valor_unitario_centavos),
            )
        )
    return normalizados


# --- Conversões ------------------------------------------------------------------------


def item_dto(item: OsItemCusto) -> ItemDTO:
    return ItemDTO(
        id=item.id,
        fase=item.fase,
        categoria_id=item.categoria_id,
        categoria_codigo=item.categoria.codigo,
        categoria_nome=item.categoria.nome,
        categoria_ordem=item.categoria.ordem,
        descricao=item.descricao,
        quantidade=item.quantidade,
        valor_unitario_centavos=item.valor_unitario_centavos,
        total_centavos=total_da_linha(item.quantidade, item.valor_unitario_centavos),
    )


def texto_do_item(categoria_nome: str, descricao: str, quantidade: Decimal, valor: int) -> str:
    """Resumo do item para o histórico, ex.: 'Mão de obra | Troca | 1,5 x R$ 33,33'."""
    return (
        f"{categoria_nome} | {descricao} | {formatacao.formatar_quantidade(quantidade)} x "
        f"{formatacao.formatar_brl(valor)}"
    )


def texto_do_campo(campo: str, valor, categorias: dict[int, str] | None = None) -> str:
    if campo == "quantidade":
        return formatacao.formatar_quantidade(valor)
    if campo == "valor_unitario_centavos":
        return formatacao.formatar_brl(valor)
    if campo == "categoria_id":
        return (categorias or {}).get(valor, str(valor))
    return str(valor)


# --- Leitura ---------------------------------------------------------------------------


def listar_categorias(ator_id: int) -> list[CategoriaDTO]:
    """Categorias ativas, na ordem de exibição."""
    carregar_ator(ator_id)
    with sessao() as s:
        return [
            CategoriaDTO(c.id, c.codigo, c.nome, c.ordem) for c in CategoriaCustoRepo(s).listar()
        ]


def sugerir_descricoes(
    ator_id: int, filial_id: int, termo: object, limite: int = SUGESTOES_PADRAO
) -> list[str]:
    """Descrições de itens já usadas em OS da filial, para o editor de itens.

    Só manutenção da filial e administrador (o papel usuario recebe ErroPermissao).
    Termo normalizado com menos de 2 caracteres: lista vazia. Mais usada primeiro, depois
    a de uso mais recente; de cada grupo, a grafia original mais frequente. No máximo
    ``limite`` (8 por padrão, nunca mais que 20).
    """
    ator = carregar_ator(ator_id)
    if not _e_int(filial_id):
        raise ErroValidacao("filial_id", "Filial inválida.")
    if ator.e_usuario or not pode_acessar_filial(ator, filial_id):
        logger.warning(
            "Permissão negada: usuario_id=%s ação=sugestões de descrição.", ator.usuario_id
        )
        raise ErroPermissao()
    if termo is not None and not isinstance(termo, str):
        raise ErroValidacao("termo", "Busca inválida.")
    if not _e_int(limite) or limite < 1:
        raise ErroValidacao("limite", "Limite inválido.")
    normalizado = normalizar_busca((termo or "")[:DESCRICAO_ITEM_MAX])
    if len(normalizado) < SUGESTAO_TERMO_MIN:
        return []
    with sessao() as s:
        return OrdemServicoRepo(s).sugestoes_de_descricao(
            filial_id, normalizado, min(limite, SUGESTOES_MAX)
        )


# --- Escrita ---------------------------------------------------------------------------
# A importação de ``ordens`` é feita dentro das funções: ``ordens`` usa as funções puras
# deste módulo, e as regras de visibilidade, permissão e histórico ficam lá.


def adicionar_item(
    ator_id: int,
    os_id: int,
    versao: int,
    fase: str,
    categoria_id: int,
    descricao: str,
    quantidade: Decimal,
    valor_unitario_centavos: int,
):
    from osapp.services import ordens

    return ordens._alterar_itens(
        ator_id,
        os_id,
        versao,
        fase,
        ("adicionar", None),
        {
            "categoria_id": categoria_id,
            "descricao": descricao,
            "quantidade": quantidade,
            "valor_unitario_centavos": valor_unitario_centavos,
        },
    )


def editar_item(ator_id: int, os_id: int, item_id: int, versao: int, alteracoes: dict):
    from osapp.services import ordens

    return ordens._alterar_itens(ator_id, os_id, versao, None, ("editar", item_id), alteracoes)


def remover_item(ator_id: int, os_id: int, item_id: int, versao: int):
    from osapp.services import ordens

    return ordens._alterar_itens(ator_id, os_id, versao, None, ("remover", item_id), {})
