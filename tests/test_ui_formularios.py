from datetime import UTC, date, datetime, time

import pytest

from osapp.ui import formularios as f

SP = "America/Sao_Paulo"


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("1234,56", 123456), ("1.234,56", 123456), ("R$ 1.234,56", 123456), ("0,00", 0)],
)
def test_ler_valor(texto, esperado):
    assert f.ler_valor(texto) == esperado


@pytest.mark.parametrize("texto", ["", None, "abc", "-10,00", "10", "10.5", "1,2"])
def test_ler_valor_invalido_tem_mensagem_em_portugues(texto):
    with pytest.raises(ValueError) as info:
        f.ler_valor(texto)
    assert str(info.value) == f.MSG_VALOR == "Valor inválido. Use o formato 1.234,56."


@pytest.mark.parametrize(("texto", "esperado"), [("1:30", 90), ("01:30", 90), ("0:01", 1)])
def test_ler_tempo(texto, esperado):
    assert f.ler_tempo(texto) == esperado


@pytest.mark.parametrize("texto", ["", None, "90", "1h30", "abc", "1:60"])
def test_ler_tempo_invalido(texto):
    with pytest.raises(ValueError) as info:
        f.ler_tempo(texto)
    assert str(info.value) == f.MSG_TEMPO


def test_ler_tempo_zero_e_recusado():
    with pytest.raises(ValueError) as info:
        f.ler_tempo("0:00")
    assert str(info.value) == f.MSG_TEMPO_ZERO


@pytest.mark.parametrize("minutos", [1, 59, 60, 90, 6005, 59_999])
def test_tempo_ida_e_volta(minutos):
    assert f.ler_tempo(f.tempo_para_campo(minutos)) == minutos
    assert f.tempo_para_campo(90) == "1:30"


@pytest.mark.parametrize("centavos", [0, 5, 123456, 9_999_999_999])
def test_valor_ida_e_volta(centavos):
    assert f.ler_valor(f.valor_para_campo(centavos)) == centavos


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


# --- Prévia das diferenças na tela Concluir OS ---------------------------------------


def previa(
    valor="120,00",
    inicio=("04/05/2026", "13:50"),
    fim=("04/05/2026", "14:30"),
    previsto=10000,
    tempo=60,
):
    return f.previa_diferencas(previsto, tempo, valor, inicio, fim, SP)


def test_previa_com_entradas_validas():
    assert previa() == (
        "+R$ 20,00 (+20,0%) - Acima do previsto",
        "-0h20 - Abaixo do previsto",  # 40 minutos realizados contra 60 previstos
    )
    assert previa(valor="100,00", fim=("04/05/2026", "14:50")) == (
        "R$ 0,00 (0,0%) - Igual ao previsto",
        "0h00 - Igual ao previsto",
    )


def test_previa_sem_percentual_quando_o_previsto_e_zero():
    assert previa(previsto=0)[0] == "+R$ 120,00 - Acima do previsto"


def test_previa_cruzando_a_meia_noite():
    assert previa(inicio=("04/05/2026", "23:30"), fim=("05/05/2026", "00:45"))[1] == (
        "+0h15 - Acima do previsto"
    )


@pytest.mark.parametrize(
    ("kwargs", "esperado"),
    [
        ({"valor": ""}, (None, "-0h20 - Abaixo do previsto")),
        ({"valor": "abc"}, (None, "-0h20 - Abaixo do previsto")),
        ({"inicio": ("04/05/2026", "")}, ("+R$ 20,00 (+20,0%) - Acima do previsto", None)),
        ({"fim": ("31/02/2026", "14:30")}, ("+R$ 20,00 (+20,0%) - Acima do previsto", None)),
        # fim antes do início: sem prévia de tempo
        ({"fim": ("04/05/2026", "13:00")}, ("+R$ 20,00 (+20,0%) - Acima do previsto", None)),
        ({"valor": None, "inicio": (None, None), "fim": (None, None)}, (None, None)),
    ],
)
def test_previa_some_enquanto_a_entrada_e_invalida(kwargs, esperado):
    assert previa(**kwargs) == esperado
