from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from osapp.formatacao import (
    formatar_brl,
    formatar_data,
    formatar_data_hora,
    formatar_duracao,
    ler_brl,
    ler_duracao,
)


@pytest.mark.parametrize(
    ("centavos", "esperado"),
    [
        (123456, "R$ 1.234,56"),
        (0, "R$ 0,00"),
        (5, "R$ 0,05"),
        (100, "R$ 1,00"),
        (99999, "R$ 999,99"),
        (100000, "R$ 1.000,00"),
        (123456789012, "R$ 1.234.567.890,12"),
        (-123456, "-R$ 1.234,56"),
    ],
)
def test_formatar_brl(centavos, esperado):
    assert formatar_brl(centavos) == esperado


@pytest.mark.parametrize("invalido", [12.5, "100", None, True])
def test_formatar_brl_rejeita_nao_inteiro(invalido):
    with pytest.raises(TypeError):
        formatar_brl(invalido)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("1234,56", 123456),
        ("1.234,56", 123456),
        ("R$ 1.234,56", 123456),
        ("R$1.234,56", 123456),
        ("R$ 1.234,56", 123456),
        ("  0,00 ", 0),
        ("0,05", 5),
        ("1.234.567.890,12", 123456789012),
    ],
)
def test_ler_brl(texto, esperado):
    assert ler_brl(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "abc",
        "1234.56",
        "1,234.56",
        "12,3",
        "12,345",
        "1.23,45",
        "1..234,56",
        "-1,00",
        "R$",
        "US$ 1,00",
        "1 234,56",
        "1234,56 reais",
        None,
        1234,
    ],
)
def test_ler_brl_invalido(texto):
    with pytest.raises(ValueError):
        ler_brl(texto)


def test_ler_brl_sem_centavos_e_em_reais():
    """Regra aprovada (prompt 13): '150' = R$ 150,00; o ponto só separa milhares."""
    assert ler_brl("150") == 15000
    assert ler_brl("150,50") == 15050
    assert ler_brl("1.234") == 123400
    assert ler_brl("R$ 1234") == 123400
    with pytest.raises(ValueError):
        ler_brl("150.50")


def test_brl_ida_e_volta():
    for centavos in (0, 1, 99, 100, 123456, 10**12 + 7):
        assert ler_brl(formatar_brl(centavos)) == centavos


def test_formatar_data():
    assert formatar_data(date(2026, 3, 5)) == "05/03/2026"
    assert formatar_data(date(999, 12, 31)) == "31/12/0999"


def test_formatar_data_de_datetime_usa_o_fuso():
    # 02:00 UTC do dia 2 ainda é dia 1 em São Paulo (UTC-3).
    dt = datetime(2026, 3, 2, 2, 0, tzinfo=UTC)
    assert formatar_data(dt, tz="America/Sao_Paulo") == "01/03/2026"


def test_formatar_data_hora_converte_fuso():
    dt = datetime(2026, 1, 15, 15, 30, tzinfo=UTC)
    assert formatar_data_hora(dt, tz="America/Sao_Paulo") == "15/01/2026 12:30"
    assert formatar_data_hora(dt, tz="Asia/Tokyo") == "16/01/2026 00:30"


def test_formatar_data_hora_vira_o_dia():
    dt = datetime(2026, 1, 1, 1, 5, tzinfo=UTC)
    assert formatar_data_hora(dt, tz="America/Sao_Paulo") == "31/12/2025 22:05"


def test_formatar_data_hora_aceita_outro_fuso_de_origem_e_naive():
    origem = datetime(2026, 1, 15, 20, 0, tzinfo=timezone(timedelta(hours=2)))
    assert formatar_data_hora(origem, tz="America/Sao_Paulo") == "15/01/2026 15:00"
    naive = datetime(2026, 1, 15, 15, 30)  # sem fuso = UTC
    assert formatar_data_hora(naive, tz="America/Sao_Paulo") == "15/01/2026 12:30"


def test_formatar_data_hora_le_os_tz_do_ambiente(monkeypatch):
    dt = datetime(2026, 1, 15, 15, 30, tzinfo=UTC)
    monkeypatch.setenv("OS_TZ", "America/Manaus")
    assert formatar_data_hora(dt) == "15/01/2026 11:30"
    monkeypatch.delenv("OS_TZ")
    assert formatar_data_hora(dt) == "15/01/2026 12:30"


@pytest.mark.parametrize(
    ("minutos", "esperado"),
    [(90, "1h30"), (0, "0h00"), (5, "0h05"), (60, "1h00"), (59, "0h59"), (6005, "100h05")],
)
def test_formatar_duracao(minutos, esperado):
    assert formatar_duracao(minutos) == esperado


def test_formatar_duracao_invalida():
    with pytest.raises(ValueError):
        formatar_duracao(-1)
    with pytest.raises(TypeError):
        formatar_duracao(1.5)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [("1:30", 90), ("01:30", 90), ("0:00", 0), ("0:05", 5), (" 2:00 ", 120), ("100:05", 6005)],
)
def test_ler_duracao(texto, esperado):
    assert ler_duracao(texto) == esperado


@pytest.mark.parametrize(
    "texto", ["", "abc", "90", "1:60", "1:5", "1h30", "-1:30", "1:30:00", ":30", "1:", None, 90]
)
def test_ler_duracao_invalida(texto):
    with pytest.raises(ValueError):
        ler_duracao(texto)
