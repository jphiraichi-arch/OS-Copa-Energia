"""Leitura e formatação dos campos de dinheiro, duração e hora (sem máscara ao vivo)."""

from __future__ import annotations

import re
from datetime import time

import pytest

from osapp.ui import leitura as L
from tests.conftest import RAIZ


@pytest.mark.parametrize(
    ("entrada", "valor", "texto"),
    [
        ("150", 15000, "150,00"),
        ("150,50", 15050, "150,50"),
        ("1.234,56", 123456, "1.234,56"),
        ("1234,56", 123456, "1.234,56"),
        ("R$ 1.234,56", 123456, "1.234,56"),
        ("R$ 15", 1500, "15,00"),
        ("  7 ", 700, "7,00"),
        ("0,01", 1, "0,01"),
        ("99.999.999,99", 9_999_999_999, "99.999.999,99"),
        ("", 0, ""),
        (None, 0, ""),
        ("0", 0, ""),
    ],
)
def test_dinheiro_aceito(entrada, valor, texto):
    assert L.ler_dinheiro(entrada) == L.Lido(valor, texto)


@pytest.mark.parametrize(
    ("entrada", "erro"),
    [
        ("150.50", L.MSG_DINHEIRO),  # formato americano recusado
        ("150,5", L.MSG_DINHEIRO),
        ("1,234.56", L.MSG_DINHEIRO),
        ("abc", L.MSG_DINHEIRO),
        ("-10", L.MSG_DINHEIRO),
        ("100.000.000,00", L.MSG_DINHEIRO_MAX),
    ],
)
def test_dinheiro_recusado_mantem_o_texto(entrada, erro):
    assert L.ler_dinheiro(entrada) == L.Lido(None, entrada, erro)


def test_texto_inicial_de_dinheiro():
    assert (L.texto_dinheiro(0), L.texto_dinheiro(15000)) == ("", "150,00")


@pytest.mark.parametrize(
    ("entrada", "valor", "texto"),
    [
        ("1:30", 90, "1:30"),
        ("01:30", 90, "1:30"),
        ("130", 90, "1:30"),
        ("2", 120, "2:00"),
        ("12", 720, "12:00"),
        ("999:59", 999 * 60 + 59, "999:59"),
        ("0:00", 0, "0:00"),
        ("", 0, ""),
    ],
)
def test_duracao_aceita(entrada, valor, texto):
    assert L.ler_duracao(entrada) == L.Lido(valor, texto)


@pytest.mark.parametrize(
    ("entrada", "erro"),
    [
        ("1:60", L.MSG_MINUTOS),
        ("190", L.MSG_MINUTOS),
        ("1000:00", L.MSG_DURACAO_MAX),
        ("1h30", L.MSG_DURACAO),
        ("1,5", L.MSG_DURACAO),
        ("1:5", L.MSG_DURACAO),
    ],
)
def test_duracao_recusada(entrada, erro):
    assert L.ler_duracao(entrada) == L.Lido(None, entrada, erro)


@pytest.mark.parametrize(
    ("entrada", "valor", "texto"),
    [
        ("13:50", time(13, 50), "13:50"),
        ("9:05", time(9, 5), "09:05"),
        ("1350", time(13, 50), "13:50"),
        ("930", time(9, 30), "09:30"),
        ("14", time(14, 0), "14:00"),
        ("0", time(0, 0), "00:00"),
        ("23:59", time(23, 59), "23:59"),
    ],
)
def test_hora_aceita(entrada, valor, texto):
    assert L.ler_hora(entrada) == L.Lido(valor, texto)


@pytest.mark.parametrize(
    ("entrada", "erro"),
    [
        ("24:00", L.MSG_HORA),
        ("2400", L.MSG_HORA),
        ("12:60", L.MSG_MINUTOS),
        ("12h", L.MSG_HORA),
        ("", L.MSG_HORA_VAZIA),
    ],
)
def test_hora_recusada(entrada, erro):
    assert L.ler_hora(entrada) == L.Lido(None, entrada, erro)


def test_formatar_e_ler_de_novo_da_o_mesmo_valor():
    for leitor in (L.ler_dinheiro, L.ler_duracao, L.ler_hora):
        for entrada in ("1", "130", "1:30", "12,00", "2359"):
            lido = leitor(entrada)
            if lido.erro is None:
                assert leitor(lido.texto).valor == lido.valor


def test_modulo_puro():
    texto = (RAIZ / "src" / "osapp" / "ui" / "leitura.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(flet|sqlalchemy|osapp\.(db|models))", texto, re.M)


def test_campos_nunca_reescrevem_o_valor_ao_digitar():
    """O on_change dos campos não pode atribuir ``.value`` (perdia dígitos em 4G)."""
    texto = (RAIZ / "src" / "osapp" / "ui" / "components" / "campos.py").read_text(encoding="utf-8")
    corpo = texto.split("def _ao_mudar", 1)[1].split("\n    def ", 1)[0]
    assert ".value =" not in corpo and "selection" not in corpo
