from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest

from osapp.services import custos
from osapp.services.custos import CategoriaDTO
from osapp.ui import formularios as f

SP = "America/Sao_Paulo"


def test_ler_data_e_hora():
    assert f.ler_data("04/05/2026") == date(2026, 5, 4)
    assert f.ler_data(" 4/5/2026 ") == date(2026, 5, 4)
    assert f.ler_hora("13:50") == time(13, 50)
    assert f.ler_hora("7:05") == time(7, 5)


@pytest.mark.parametrize("texto", ["", None, "2026-05-04", "31/02/2026", "04/13/2026", "4/5/26"])
def test_ler_data_invalida(texto):
    with pytest.raises(ValueError) as info:
        f.ler_data(texto)
    assert str(info.value) == f.MSG_DATA


@pytest.mark.parametrize("texto", ["", None, "1350", "24:00", "13:60", "13:5", "13h50"])
def test_ler_hora_invalida(texto):
    with pytest.raises(ValueError) as info:
        f.ler_hora(texto)
    assert str(info.value) == f.MSG_HORA


def test_data_e_hora_locais_viram_utc():
    assert f.ler_data_hora("04/05/2026", "13:50", SP) == datetime(2026, 5, 4, 16, 50, tzinfo=UTC)
    assert f.ler_data_hora("04/05/2026", "13:50", "UTC") == datetime(2026, 5, 4, 13, 50, tzinfo=UTC)
    resultado = f.para_utc(date(2026, 5, 4), time(13, 50), "Asia/Tokyo")
    assert resultado == datetime(2026, 5, 4, 4, 50, tzinfo=UTC)
    assert resultado.utcoffset().total_seconds() == 0


def test_servico_que_cruza_a_meia_noite():
    # 23:30 de um dia até 00:45 do dia seguinte, em São Paulo: 75 minutos.
    inicio = f.ler_data_hora("04/05/2026", "23:30", SP)
    fim = f.ler_data_hora("05/05/2026", "00:45", SP)
    assert inicio == datetime(2026, 5, 5, 2, 30, tzinfo=UTC)
    assert fim == datetime(2026, 5, 5, 3, 45, tzinfo=UTC)
    assert (fim - inicio).total_seconds() == 75 * 60
    # A meia-noite em UTC cai às 21:00 locais: o dia local não muda, o dia UTC muda.
    antes = f.ler_data_hora("04/05/2026", "20:30", SP)
    depois = f.ler_data_hora("04/05/2026", "21:30", SP)
    assert (antes.day, depois.day) == (4, 5) and (depois - antes).total_seconds() == 3600


def test_partes_locais_e_ida_e_volta():
    instante = datetime(2026, 5, 5, 2, 30, tzinfo=UTC)
    assert f.partes_locais(instante, SP) == ("04/05/2026", "23:30")
    assert f.ler_data_hora(*f.partes_locais(instante, SP), SP) == instante


def test_somente_alterados():
    original = {"titulo": "A", "valor_previsto_centavos": 100, "filial_id": 1}
    atual = {"titulo": "B", "valor_previsto_centavos": 100, "filial_id": 1}
    assert f.somente_alterados(original, atual) == {"titulo": "B"}
    assert f.somente_alterados(original, dict(original)) == {}
    assert f.somente_alterados({}, {"titulo": "B"}) == {"titulo": "B"}


# --- Itens de custo: dos campos para os argumentos dos serviços ----------------------

CATEGORIAS = [
    CategoriaDTO(1, "MAO_DE_OBRA", "Mão de obra", 1),
    CategoriaDTO(2, "PECAS", "Peças", 2),
]


def digitado(**kw):
    valores = {
        "categoria_id": 2,
        "descricao": "  Rolamento  ",
        "quantidade": "1,5",
        "valor_unitario_centavos": 3333,
    }
    valores.update(kw)
    return valores


def test_ler_item_valido_vira_item_entrada():
    item, erros = f.ler_item(CATEGORIAS, custos.FASE_PREVISTO, 7, None, digitado())
    assert erros == {}
    assert item.chave == 7 and item.id is None
    assert (item.categoria_nome, item.categoria_ordem, item.descricao) == ("Peças", 2, "Rolamento")
    assert item.quantidade == Decimal("1.50")
    assert item.total_centavos == 5000  # 1,5 x 33,33 = 49,995 -> 50,00 (ROUND_HALF_UP)
    assert f.para_entrada([item]) == [custos.ItemEntrada(2, "Rolamento", Decimal("1.50"), 3333)]


@pytest.mark.parametrize(("texto", "esperado"), [("1", "1.00"), ("1,5", "1.50"), ("1,50", "1.50")])
def test_ler_item_quantidade_aceita_formatos(texto, esperado):
    item, _ = f.ler_item(CATEGORIAS, "PREVISTO", 1, None, digitado(quantidade=texto))
    assert item.quantidade == Decimal(esperado)


@pytest.mark.parametrize(
    ("kw", "campo", "mensagem"),
    [
        ({"categoria_id": None}, "categoria_id", f.MSG_CATEGORIA),
        ({"categoria_id": 99}, "categoria_id", f.MSG_CATEGORIA),
        ({"descricao": "  "}, "descricao", "Informe a descrição do item."),
        ({"quantidade": "1.5"}, "quantidade", f.MSG_QUANTIDADE),
        ({"quantidade": ""}, "quantidade", f.MSG_QUANTIDADE),
        ({"quantidade": "0"}, "quantidade", "A quantidade deve ficar entre 0,01 e 99.999,99."),
        ({"quantidade": "1,555"}, "quantidade", f.MSG_QUANTIDADE),
        ({"valor_unitario_centavos": None}, "valor_unitario_centavos", "Informe um valor válido."),
    ],
)
def test_ler_item_erros_por_campo(kw, campo, mensagem):
    item, erros = f.ler_item(CATEGORIAS, "PREVISTO", 1, None, digitado(**kw))
    assert item is None
    assert erros[campo] == mensagem


def test_valor_zero_e_aceito():
    item, erros = f.ler_item(CATEGORIAS, "PREVISTO", 1, None, digitado(valor_unitario_centavos=0))
    assert erros == {} and item.total_centavos == 0


def test_alteracoes_do_item_so_o_que_mudou():
    antes, _ = f.ler_item(CATEGORIAS, "PREVISTO", 1, 10, digitado())
    depois, _ = f.ler_item(
        CATEGORIAS, "PREVISTO", 1, 10, digitado(categoria_id=1, valor_unitario_centavos=4000)
    )
    assert f.alteracoes_do_item(antes, depois) == {
        "categoria_id": 1,
        "valor_unitario_centavos": 4000,
    }
    assert f.alteracoes_do_item(antes, antes) == {}


def test_copiar_itens_previstos_para_realizado():
    a, _ = f.ler_item(CATEGORIAS, "PREVISTO", 1, 10, digitado())
    b, _ = f.ler_item(CATEGORIAS, "PREVISTO", 2, 11, digitado(categoria_id=1))
    copias = f.copiar_itens([a, b], custos.FASE_REALIZADO, 100)
    assert [(c.chave, c.id, c.fase) for c in copias] == [
        (100, None, "REALIZADO"),
        (101, None, "REALIZADO"),
    ]
    assert copias[0].descricao == a.descricao and copias[0].quantidade == a.quantidade


def test_resumo_previa_usa_o_calculo_do_servico():
    a, _ = f.ler_item(CATEGORIAS, "PREVISTO", 1, None, digitado())  # Peças 50,00
    b, _ = f.ler_item(
        CATEGORIAS,
        "PREVISTO",
        2,
        None,
        digitado(categoria_id=1, quantidade="2", valor_unitario_centavos=1000),
    )  # Mão de obra 20,00
    resumo = f.resumo_previa([a, b])
    assert [(c.categoria_nome, c.previsto_centavos) for c in resumo.por_categoria] == [
        ("Mão de obra", 2000),
        ("Peças", 5000),
    ]
    assert resumo.total_previsto_centavos == 7000


def test_item_local_de_um_dto():
    dto = custos.ItemDTO(
        5, "REALIZADO", 1, "MAO_DE_OBRA", "Mão de obra", 1, "Troca", Decimal("2.00"), 1500, 3000
    )
    item = f.item_local(dto)
    assert (item.chave, item.id, item.fase, item.total_centavos) == (5, 5, "REALIZADO", 3000)
    assert f.itens_da_fase([dto], "PREVISTO") == []


# --- Conclusão: data + CampoHora --------------------------------------------------------


def test_instante_converte_do_fuso_local_para_utc():
    assert f.instante("04/05/2026", time(13, 50), SP) == datetime(2026, 5, 4, 16, 50, tzinfo=UTC)
    with pytest.raises(ValueError):
        f.instante("04/05/2026", None, SP)
    with pytest.raises(ValueError):
        f.instante("31/02/2026", time(13, 50), SP)


def test_previa_tempo():
    inicio, fim = ("04/05/2026", time(13, 50)), ("04/05/2026", time(14, 30))
    assert f.previa_tempo(60, inicio, fim, SP) == "-0h20 - Abaixo do previsto"
    assert f.previa_tempo(40, inicio, fim, SP) == "0h00 - Igual ao previsto"
    meia_noite = (("04/05/2026", time(23, 30)), ("05/05/2026", time(0, 45)))
    assert f.previa_tempo(60, *meia_noite, SP) == "+0h15 - Acima do previsto"
    assert f.previa_tempo(60, inicio, ("04/05/2026", None), SP) is None
    assert f.previa_tempo(60, fim, inicio, SP) is None  # fim antes do início
