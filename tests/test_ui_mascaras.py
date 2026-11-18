from datetime import time

import pytest

from osapp.ui import mascaras as m


def sequencia(funcao, teclas, **kw):
    """Simula a digitação: cada tecla é acrescentada ao que o campo mostra."""
    texto, vistos = "", []
    for tecla in teclas:
        texto = funcao(texto + tecla, **kw).texto
        vistos.append(texto)
    return vistos


def test_dinheiro_sequencias_do_enunciado():
    assert m.mascara_dinheiro("").texto == "0,00"
    assert sequencia(m.mascara_dinheiro, "219") == ["0,02", "0,21", "2,19"]
    assert sequencia(m.mascara_dinheiro, "1000") == ["0,01", "0,10", "1,00", "10,00"]
    assert m.mascara_dinheiro("123456").texto == "1.234,56"
    assert m.mascara_dinheiro("123456").valor == 123456


def test_dinheiro_apagar_colar_e_limite():
    assert m.mascara_dinheiro("2,1").texto == "0,21"  # backspace sobre "2,19"
    assert m.mascara_dinheiro("0,0").valor == 0
    assert m.mascara_dinheiro("R$ 1.234,56").valor == 123456  # colado
    assert m.mascara_dinheiro("abc").texto == "0,00"
    cheio = m.mascara_dinheiro("99999999999999")  # 14 dígitos: só os 10 primeiros
    assert (cheio.texto, cheio.valor) == ("99.999.999,99", 9_999_999_999)
    assert m.mascara_dinheiro("0002").texto == "0,02"  # zeros à esquerda


def test_duracao_sequencias_do_enunciado():
    assert m.mascara_hora("").texto == "0:00"
    assert sequencia(m.mascara_hora, "130") == ["0:01", "0:13", "1:30"]
    assert m.mascara_hora("219").texto == "2:19"
    assert sequencia(m.mascara_hora, "1000") == ["0:01", "0:10", "1:00", "10:00"]
    assert m.mascara_hora("130").valor == 90


def test_duracao_minutos_invalidos_e_limites():
    r = m.mascara_hora("75")
    assert (r.texto, r.erro, r.valor) == ("0:75", "Minutos devem ficar entre 00 e 59.", None)
    for minutos in range(60, 100):
        assert m.mascara_hora(str(minutos)).erro == m.MSG_MINUTOS
    assert m.mascara_hora("99959").valor == 999 * 60 + 59
    assert m.mascara_hora("9995999").texto == "999:59"  # dígitos a mais são ignorados
    assert m.mascara_hora("1:3").texto == "0:13"  # backspace sobre "1:30"
    assert m.mascara_hora("12:30").valor == 750  # colado


def test_relogio():
    assert m.mascara_hora("", m.RELOGIO).texto == "00:00"
    assert sequencia(m.mascara_hora, "1350", tipo=m.RELOGIO) == ["00:01", "00:13", "01:35", "13:50"]
    assert m.mascara_hora("1350", m.RELOGIO).valor == time(13, 50)
    assert m.mascara_hora("12:30", m.RELOGIO).valor == time(12, 30)
    assert m.mascara_hora("2400", m.RELOGIO).erro == "Hora inválida."
    assert m.mascara_hora("2359", m.RELOGIO).valor == time(23, 59)
    assert m.mascara_hora("1375", m.RELOGIO).erro == m.MSG_MINUTOS
    assert m.mascara_hora("123456", m.RELOGIO).texto == "12:34"  # no máximo 4 dígitos


@pytest.mark.parametrize(
    ("funcao", "valor", "esperado"),
    [
        (m.digitos_de_centavos, 21900, "21900"),
        (m.digitos_de_centavos, 0, ""),
        (m.digitos_de_minutos, 90, "130"),
        (m.digitos_de_minutos, 600, "1000"),
        (m.digitos_de_hora, time(13, 50), "1350"),
        (m.digitos_de_hora, time(0, 0), ""),
    ],
)
def test_valor_inicial_volta_a_mascara(funcao, valor, esperado):
    assert funcao(valor) == esperado


@pytest.mark.parametrize(
    ("digitos", "antigo", "novo", "esperado"),
    [
        ("", "0,00", "20,00", "2"),  # cursor no início: o dígito entra pela direita
        ("2", "0,02", "0,021", "21"),  # cursor no fim
        ("21", "0,21", "0,2", "2"),  # backspace no fim
        ("219", "2,19", "2,9", "21"),  # apagar no meio tira o último dígito guardado
        ("219", "2,19", "219", "21"),  # apagar só a vírgula também tira um
        ("219", "2,19", "12:30", "1230"),  # selecionar tudo e colar
        ("219", "2,19", "", ""),  # apagar tudo
        ("9999999999", "99.999.999,99", "99.999.999,999", "9999999999"),  # limite
        ("", "0:00", "0:00abc", ""),  # letras são ignoradas
    ],
)
def test_editar_digitos(digitos, antigo, novo, esperado):
    assert m.editar_digitos(digitos, antigo, novo, m.DIGITOS_MAX_DINHEIRO) == esperado
