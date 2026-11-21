"""Prompt 13: itens de custo nos serviços."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from osapp import formatacao
from osapp.db import sessao
from osapp.models import CategoriaCusto, OrdemServico, OsEvento
from osapp.services import custos, ordens, relogio, status
from osapp.services.custos import ItemEntrada, calcular_resumo, total_da_linha
from osapp.services.erros import (
    ErroAutenticacao,
    ErroConflito,
    ErroNaoEncontrado,
    ErroPermissao,
    ErroValidacao,
)
from tests.fabricas import NOTA, categoria_id, tipo_id

T0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
INICIO, FIM = T0 - timedelta(hours=3), T0 - timedelta(hours=1)


@pytest.fixture(autouse=True)
def relogio_fixo(monkeypatch):
    monkeypatch.setattr(relogio, "agora", lambda: T0)


def item(valor=1000, quantidade="1", descricao="Item", codigo="OUTROS"):
    return ItemEntrada(categoria_id(codigo), descricao, Decimal(quantidade), valor)


def criar(ator_id, itens=None, **extras):
    dados = {
        "tipo_id": tipo_id(),
        "prioridade": "media",
    }
    dados.update(extras)
    return ordens.criar_os(
        ator_id,
        "Troca de rolamento",
        "Descrição.",
        itens if itens is not None else [item(1000), item(2000, codigo="MAO_DE_OBRA")],
        60,
        **dados,
    )


def preparar(cenario, destino):
    """OS de marina com 2 itens previstos; iniciada e concluída por pedro com 2 realizados."""
    d = criar(cenario["marina"])
    if destino in (status.EM_EXECUCAO, status.CONCLUIDA):
        d = ordens.iniciar_execucao(cenario["pedro"], d.id, d.versao)
    if destino == status.CONCLUIDA:
        d = ordens.concluir_os(
            cenario["pedro"],
            d.id,
            d.versao,
            [item(1500), item(2500, codigo="MAO_DE_OBRA")],
            INICIO,
            FIM,
            "Feito.",
            NOTA,
        )
    return d


def estado(os_id):
    with sessao() as s:
        o = s.get(OrdemServico, os_id)
        n = s.scalar(select(func.count()).select_from(OsEvento).where(OsEvento.os_id == os_id))
        return (
            o.versao,
            tuple(
                (i.id, i.fase, i.descricao, i.quantidade, i.valor_unitario_centavos)
                for i in o.itens
            ),
            n,
        )


def eventos(cenario, os_id):
    return [
        (e.tipo, e.campo, e.valor_antigo, e.valor_novo)
        for e in ordens.listar_eventos(cenario["admin"], os_id)
    ]


# --- Cálculo ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("quantidade", "valor", "esperado"),
    [
        ("1.5", 3333, 5000),  # 49,995 arredonda para cima (ROUND_HALF_UP)
        ("0.01", 1, 0),  # 0,0001 centavo
        ("0.01", 50, 1),  # 0,5 centavo -> 1
        ("0.01", 49, 0),
        ("2", 1000, 2000),
        ("99999.99", 9_999_999_999, 999_999_899_900_000),  # o maior caso: sem estouro
    ],
)
def test_total_da_linha(quantidade, valor, esperado):
    assert total_da_linha(Decimal(quantidade), valor) == esperado
    assert isinstance(total_da_linha(Decimal(quantidade), valor), int)


@dataclass(frozen=True)
class Previa:
    fase: str
    categoria_id: int
    categoria_nome: str
    categoria_ordem: int
    quantidade: Decimal
    valor_unitario_centavos: int


def test_resumo_por_categoria_e_total():
    itens = [
        Previa("PREVISTO", 1, "Mão de obra", 1, Decimal("2"), 5000),
        Previa("PREVISTO", 4, "Outros", 4, Decimal("1"), 1000),
        Previa("REALIZADO", 1, "Mão de obra", 1, Decimal("1.5"), 3333),
        Previa("REALIZADO", 2, "Peças/materiais", 2, Decimal("1"), 700),  # só realizado
    ]
    r = calcular_resumo(itens)
    linhas = {c.categoria_nome: c for c in r.por_categoria}
    assert [c.categoria_nome for c in r.por_categoria] == [
        "Mão de obra",
        "Peças/materiais",
        "Outros",
    ]
    assert (linhas["Mão de obra"].previsto_centavos, linhas["Mão de obra"].realizado_centavos) == (
        10000,
        5000,
    )
    assert (
        linhas["Mão de obra"].diferenca_centavos,
        linhas["Mão de obra"].diferenca_percentual,
    ) == (-5000, -50.0)
    assert (
        linhas["Peças/materiais"].previsto_centavos,
        linhas["Peças/materiais"].diferenca_percentual,
    ) == (0, None)
    assert (linhas["Outros"].realizado_centavos, linhas["Outros"].diferenca_centavos) == (0, -1000)
    assert (r.total_previsto_centavos, r.total_realizado_centavos) == (11000, 5700)
    assert (r.diferenca_centavos, r.diferenca_percentual) == (-5300, -48.18)


def test_resumo_com_previsto_zero_e_vazio():
    r = calcular_resumo([Previa("REALIZADO", 4, "Outros", 4, Decimal("1"), 500)])
    assert (r.total_previsto_centavos, r.diferenca_percentual) == (0, None)
    vazio = calcular_resumo([])
    assert (vazio.por_categoria, vazio.total_previsto_centavos, vazio.diferenca_percentual) == (
        (),
        0,
        None,
    )


def test_detalhe_traz_itens_e_resumo(cenario):
    d = criar(cenario["marina"], [item(3333, "1.5", codigo="MAO_DE_OBRA"), item(1000)])
    assert [(i.fase, i.categoria_codigo, i.total_centavos) for i in d.itens] == [
        ("PREVISTO", "MAO_DE_OBRA", 5000),
        ("PREVISTO", "OUTROS", 1000),
    ]
    assert d.resumo_custos.total_previsto_centavos == 6000
    assert ordens.listar_os(cenario["marina"]).itens[0].total_previsto_centavos == 6000


# --- Texto digitado --------------------------------------------------------------------


def test_ler_brl_e_quantidade():
    assert formatacao.ler_brl("150") == 15000
    assert formatacao.ler_brl("150,50") == 15050
    with pytest.raises(ValueError):
        formatacao.ler_brl("150.50")
    assert formatacao.ler_quantidade("1") == Decimal("1.00")
    assert formatacao.ler_quantidade("1,5") == Decimal("1.50")
    assert formatacao.ler_quantidade("1,50") == Decimal("1.50")
    for invalido in ("1.5", "1,505", "", "abc", "-1", "0,5,5"):
        with pytest.raises(ValueError):
            formatacao.ler_quantidade(invalido)
    assert [formatacao.formatar_quantidade(Decimal(q)) for q in ("1.50", "2.00", "0.25")] == [
        "1,5",
        "2",
        "0,25",
    ]


# --- Matriz de permissões dos itens ----------------------------------------------------

ATORES = ["marina", "joao", "pedro", "carlos", "admin", "inativa"]
#          criadora  colega  executor  outra filial  admin  inativa
OK, PERM, NAOENC, AUT = "ok", ErroPermissao, ErroNaoEncontrado, ErroAutenticacao
# Prompt 17: previsto é da manutenção da filial (todos os três são 'manutencao').
_P_ABERTA = [OK, OK, OK, NAOENC, OK, AUT]
_P_FECHADA = [PERM, PERM, PERM, NAOENC, OK, AUT]
_R_ABERTA = [PERM, PERM, PERM, NAOENC, PERM, AUT]
ESPERADO = {
    ("PREVISTO", status.ABERTA): _P_ABERTA,
    ("PREVISTO", status.EM_EXECUCAO): _P_ABERTA,
    ("PREVISTO", status.CONCLUIDA): _P_FECHADA,
    ("REALIZADO", status.ABERTA): _R_ABERTA,
    ("REALIZADO", status.EM_EXECUCAO): _R_ABERTA,
    ("REALIZADO", status.CONCLUIDA): _P_FECHADA,
}
# Antes da conclusão não existe item realizado para editar ou remover: só "adicionar".
CELULAS = [
    (op, fase, st, ator, ESPERADO[(fase, st)][i])
    for op in ("adicionar", "editar", "remover")
    for (fase, st) in ESPERADO
    for i, ator in enumerate(ATORES)
    if not (op != "adicionar" and fase == "REALIZADO" and st != status.CONCLUIDA)
]
FLAG = {"PREVISTO": "pode_editar_itens_previstos", "REALIZADO": "pode_editar_itens_realizados"}


def executar(op, ator_id, d, fase):
    alvo = next((i for i in d.itens if i.fase == fase), None)
    if op == "adicionar":
        return custos.adicionar_item(
            ator_id, d.id, d.versao, fase, categoria_id("OUTROS"), "Novo", Decimal("2"), 300
        )
    if op == "editar":
        return custos.editar_item(
            ator_id, d.id, alvo.id, d.versao, {"valor_unitario_centavos": 777}
        )
    return custos.remover_item(ator_id, d.id, alvo.id, d.versao)


def test_a_matriz_de_itens_tem_84_celulas():
    assert len(CELULAS) == 84


@pytest.mark.parametrize(
    ("op", "fase", "st", "ator", "esperado"),
    CELULAS,
    ids=[f"{op}-{fase}-{st}-{ator}" for op, fase, st, ator, _ in CELULAS],
)
def test_matriz_de_permissoes_dos_itens(cenario, op, fase, st, ator, esperado):
    d = preparar(cenario, st)
    antes = estado(d.id)
    if esperado in (OK, PERM):
        assert getattr(ordens.obter_os(cenario[ator], d.id).acoes, FLAG[fase]) is (esperado == OK)
    if esperado == OK:
        depois = executar(op, cenario[ator], d, fase)
        assert depois.versao == d.versao + 1
        assert estado(d.id) != antes
        tipo = {
            "adicionar": "ITEM_ADICIONADO",
            "editar": "ITEM_ALTERADO",
            "remover": "ITEM_REMOVIDO",
        }
        assert eventos(cenario, d.id)[-1][0] == tipo[op]
    else:
        with pytest.raises(esperado):
            executar(op, cenario[ator], d, fase)
        assert estado(d.id) == antes


# --- Regras e eventos ------------------------------------------------------------------


def test_eventos_de_cada_operacao(cenario):
    d = criar(
        cenario["marina"],
        [item(1000, descricao="Rolamento"), item(2000, codigo="MAO_DE_OBRA", descricao="Hora")],
    )
    assert eventos(cenario, d.id)[1:] == [
        ("ITEM_ADICIONADO", "item 1", None, "Outros | Rolamento | 1 x R$ 10,00"),
        ("ITEM_ADICIONADO", "item 2", None, "Mão de obra | Hora | 1 x R$ 20,00"),
    ]
    d = custos.adicionar_item(
        cenario["marina"],
        d.id,
        d.versao,
        "PREVISTO",
        categoria_id("PECAS_MATERIAIS"),
        "Correia",
        Decimal("1.5"),
        3333,
    )
    assert d.versao == 2
    assert eventos(cenario, d.id)[-1] == (
        "ITEM_ADICIONADO",
        "item 3",
        None,
        "Peças/materiais | Correia | 1,5 x R$ 33,33",
    )
    d = custos.editar_item(
        cenario["marina"],
        d.id,
        3,
        d.versao,
        {"quantidade": Decimal("2"), "valor_unitario_centavos": 4000, "descricao": "Correia"},
    )
    assert d.versao == 3
    assert eventos(cenario, d.id)[-2:] == [
        ("ITEM_ALTERADO", "item 3 - quantidade", "1,5", "2"),
        ("ITEM_ALTERADO", "item 3 - valor unitário", "R$ 33,33", "R$ 40,00"),
    ]
    d = custos.editar_item(
        cenario["marina"], d.id, 3, d.versao, {"categoria_id": categoria_id("OUTROS")}
    )
    assert eventos(cenario, d.id)[-1] == (
        "ITEM_ALTERADO",
        "item 3 - categoria",
        "Peças/materiais",
        "Outros",
    )
    sem_mudanca = custos.editar_item(
        cenario["marina"], d.id, 3, d.versao, {"descricao": " Correia "}
    )
    assert sem_mudanca.versao == d.versao and len(eventos(cenario, d.id)) == 7
    d = custos.remover_item(cenario["marina"], d.id, 3, d.versao)
    assert eventos(cenario, d.id)[-1] == (
        "ITEM_REMOVIDO",
        "item 3",
        "Outros | Correia | 2 x R$ 40,00",
        None,
    )
    assert d.resumo_custos.total_previsto_centavos == 3000


def test_previsto_pode_ficar_vazio_so_enquanto_aberta(cenario):
    """Prompt 17: o previsto é opcional na criação; iniciar exige o previsto completo."""
    d = criar(cenario["marina"], [item(1000)])
    vazia = custos.remover_item(cenario["marina"], d.id, d.itens[0].id, d.versao)
    assert vazia.itens == () and ordens.PENDENCIA_VALOR in vazia.pendencias_para_iniciar
    with pytest.raises(ErroValidacao):
        ordens.iniciar_execucao(cenario["pedro"], vazia.id, vazia.versao)
    d = custos.adicionar_item(
        cenario["marina"], d.id, vazia.versao, "PREVISTO", categoria_id(), "X", Decimal("1"), 1
    )
    d = ordens.iniciar_execucao(cenario["pedro"], d.id, d.versao)
    with pytest.raises(ErroValidacao):  # depois de iniciada, o último previsto fica
        custos.remover_item(cenario["pedro"], d.id, d.itens[0].id, d.versao)
    antes = estado(d.id)
    with pytest.raises(ErroValidacao) as info:
        ordens.concluir_os(cenario["pedro"], d.id, d.versao, [], INICIO, FIM, "Feito.", NOTA)
    assert info.value.campo == "itens_realizados" and estado(d.id) == antes
    c = ordens.concluir_os(
        cenario["pedro"], d.id, d.versao, [item(900)], INICIO, FIM, "Feito.", NOTA
    )
    realizado = next(i for i in c.itens if i.fase == "REALIZADO")
    with pytest.raises(ErroValidacao):  # nem o admin deixa a conclusão sem item realizado
        custos.remover_item(cenario["admin"], c.id, realizado.id, c.versao)


def test_criacao_sem_item_vale_e_item_invalido_e_recusado(cenario):
    for invalido in ([object()], "item"):
        with pytest.raises(ErroValidacao):
            ordens.criar_os(cenario["marina"], "Título", "Descrição.", invalido, 60)
    with sessao() as s:
        assert s.scalar(select(func.count()).select_from(OrdemServico)) == 0
    for vazio in ([], None):
        d = ordens.criar_os(cenario["marina"], "Título", "Descrição.", vazio)
        assert d.itens == () and d.tempo_previsto_minutos is None
        assert d.pendencias_para_iniciar == (
            ordens.PENDENCIA_TEMPO,
            ordens.PENDENCIA_VALOR,
            ordens.PENDENCIA_TIPO,
            ordens.PENDENCIA_PRIORIDADE,
        )


@pytest.mark.parametrize("op", ["adicionar", "editar", "remover"])
def test_versao_desatualizada(cenario, op):
    d = criar(cenario["marina"])
    custos.adicionar_item(
        cenario["marina"], d.id, d.versao, "PREVISTO", categoria_id(), "X", Decimal("1"), 1
    )
    antes = estado(d.id)
    with pytest.raises(ErroConflito):
        executar(op, cenario["marina"], d, "PREVISTO")  # d.versao ficou velha
    assert estado(d.id) == antes


@pytest.mark.parametrize(
    ("dados", "campo"),
    [
        ({"descricao": ""}, "descricao"),
        ({"descricao": "d" * 201}, "descricao"),
        ({"quantidade": Decimal("0")}, "quantidade"),
        ({"quantidade": Decimal("0.001")}, "quantidade"),
        ({"quantidade": Decimal("100000")}, "quantidade"),
        ({"quantidade": 1.5}, "quantidade"),
        ({"quantidade": "1,5"}, "quantidade"),
        ({"valor_unitario_centavos": -1}, "valor_unitario_centavos"),
        ({"valor_unitario_centavos": 10_000_000_000}, "valor_unitario_centavos"),
        ({"valor_unitario_centavos": 10.0}, "valor_unitario_centavos"),
        ({"categoria_id": 9999}, "categoria_id"),
    ],
)
def test_validacao_do_item(cenario, dados, campo):
    d = criar(cenario["marina"])
    antes = estado(d.id)
    base = {
        "categoria_id": categoria_id(),
        "descricao": "Item",
        "quantidade": Decimal("1"),
        "valor_unitario_centavos": 100,
    }
    base.update(dados)
    with pytest.raises(ErroValidacao) as info:
        custos.adicionar_item(cenario["marina"], d.id, d.versao, "PREVISTO", **base)
    assert info.value.campo == campo
    with pytest.raises(ErroValidacao):
        custos.editar_item(cenario["marina"], d.id, d.itens[0].id, d.versao, dados)
    assert estado(d.id) == antes


def test_limites_aceitos_e_fase_e_categoria(cenario):
    d = criar(cenario["marina"], [item(9_999_999_999, "99999.99", "d" * 200), item(0, "0.01")])
    assert d.resumo_custos.total_previsto_centavos == 999_999_899_900_000
    with pytest.raises(ErroValidacao):
        custos.adicionar_item(
            cenario["marina"], d.id, d.versao, "OUTRA", categoria_id(), "X", Decimal("1"), 1
        )
    with sessao() as s:
        s.scalars(
            select(CategoriaCusto).where(CategoriaCusto.codigo == "OUTROS")
        ).one().ativo = False
    with pytest.raises(ErroValidacao):  # categoria desativada
        custos.adicionar_item(
            cenario["marina"], d.id, d.versao, "PREVISTO", categoria_id(), "X", Decimal("1"), 1
        )
    assert "OUTROS" not in [c.codigo for c in custos.listar_categorias(cenario["marina"])]


def test_no_maximo_100_itens_por_fase(cenario):
    d = criar(cenario["marina"], [item(1)] * 100)
    with pytest.raises(ErroValidacao):
        custos.adicionar_item(
            cenario["marina"], d.id, d.versao, "PREVISTO", categoria_id(), "X", Decimal("1"), 1
        )
    with pytest.raises(ErroValidacao):
        criar(cenario["marina"], [item(1)] * 101)


def test_item_de_outra_os_e_id_invalido(cenario):
    a, b = criar(cenario["marina"]), criar(cenario["marina"])
    for item_id in (b.itens[0].id, 9999, None, "1"):
        with pytest.raises(ErroNaoEncontrado):
            custos.editar_item(cenario["marina"], a.id, item_id, a.versao, {"descricao": "X"})
    with pytest.raises(ErroPermissao):  # campo que não é do item
        custos.editar_item(cenario["marina"], a.id, a.itens[0].id, a.versao, {"os_id": b.id})


def test_listar_categorias(cenario):
    assert [c.codigo for c in custos.listar_categorias(cenario["joao"])] == [
        "MAO_DE_OBRA",
        "PECAS_MATERIAIS",
        "SERVICOS_TERCEIROS",
        "OUTROS",
    ]
    with pytest.raises(ErroAutenticacao):
        custos.listar_categorias(cenario["inativa"])
