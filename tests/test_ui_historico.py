from datetime import UTC, datetime

import pytest

from osapp.services.ordens import CAMPO_FILIAL, CAMPOS_PREVISTO, CAMPOS_REALIZADO, EventoDTO
from osapp.ui import historico
from osapp.ui.historico import frase, texto_diferenca_tempo, texto_diferenca_valor

T = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


def ev(tipo, campo=None, antigo=None, novo=None) -> EventoDTO:
    return EventoDTO(T, "Marina Teste", tipo, campo, antigo, novo)


@pytest.fixture(autouse=True)
def fuso(monkeypatch):
    monkeypatch.setenv("OS_TZ", "America/Sao_Paulo")


def test_criacao():
    assert frase(ev("CRIACAO")) == "OS criada"


@pytest.mark.parametrize(
    ("antigo", "novo", "esperado"),
    [
        ("ABERTA", "EM_EXECUCAO", "Status: Aberta -> Em execução"),
        ("EM_EXECUCAO", "ABERTA", "Status: Em execução -> Aberta"),
        ("EM_EXECUCAO", "CONCLUIDA", "Status: Em execução -> Concluída"),
        ("ABERTA", "CANCELADA", "Status: Aberta -> CANCELADA"),  # status futuro: sem quebrar
    ],
)
def test_status(antigo, novo, esperado):
    assert frase(ev("STATUS", "status", antigo, novo)) == esperado


@pytest.mark.parametrize(
    ("campo", "antigo", "novo", "esperado"),
    [
        (
            "titulo",
            "Troca de rolamento",
            "Troca do motor",
            "Título: Troca de rolamento -> Troca do motor",
        ),
        (
            "descricao",
            "Esteira com ruído.",
            "Esteira parada.",
            "Descrição: Esteira com ruído. -> Esteira parada.",
        ),
        ("valor_previsto_centavos", "10000", "15000", "Valor previsto: R$ 100,00 -> R$ 150,00"),
        ("valor_previsto_centavos", "0", "123456789", "Valor previsto: R$ 0,00 -> R$ 1.234.567,89"),
        ("tempo_previsto_minutos", "60", "90", "Tempo previsto: 1h00 -> 1h30"),
        ("filial_id", "F001", "F002", "Filial: F001 -> F002"),
        ("valor_realizado_centavos", "12000", "9000", "Valor realizado: R$ 120,00 -> R$ 90,00"),
        (
            "inicio_realizado",
            "2026-05-04T16:50:00+00:00",
            "2026-05-04T17:00:00+00:00",
            "Início: 04/05/2026 13:50 -> 04/05/2026 14:00",
        ),
        (
            "fim_realizado",
            "2026-05-04T17:30:00+00:00",
            "2026-05-05T02:10:00+00:00",
            "Fim: 04/05/2026 14:30 -> 04/05/2026 23:10",
        ),
        (
            "descricao_realizado",
            "Rolamento trocado.",
            "Rolamento e correia trocados.",
            "Descrição do que foi feito: Rolamento trocado. -> Rolamento e correia trocados.",
        ),
    ],
)
def test_edicao_de_cada_campo(campo, antigo, novo, esperado):
    assert frase(ev("EDICAO", campo, antigo, novo)) == esperado


@pytest.mark.parametrize(
    ("campo", "novo", "esperado"),
    [
        ("valor_realizado_centavos", "12000", "Valor realizado: R$ 120,00"),
        ("inicio_realizado", "2026-05-04T16:50:00+00:00", "Início: 04/05/2026 13:50"),
        ("fim_realizado", "2026-05-04T17:30:00+00:00", "Fim: 04/05/2026 14:30"),
        (
            "descricao_realizado",
            "Rolamento trocado.",
            "Descrição do que foi feito: Rolamento trocado.",
        ),
    ],
)
def test_realizado_de_cada_campo(campo, novo, esperado):
    assert frase(ev("REALIZADO", campo, None, novo)) == esperado


def test_todo_campo_editavel_tem_rotulo_e_formatador():
    assert set(historico.CAMPOS) == {
        "status",
        *CAMPOS_PREVISTO,
        *CAMPOS_REALIZADO,
        CAMPO_FILIAL,
    }


def test_texto_longo_e_cortado_e_quebras_de_linha_viram_espaco():
    f = frase(ev("EDICAO", "descricao", "a\nb", "x" * 300))
    assert f.startswith("Descrição: a b -> ") and f.endswith("…")
    assert len(f) < 120


def test_valores_inesperados_nao_quebram():
    assert frase(ev("EDICAO", "valor_previsto_centavos", "abc", "150")) == (
        "Valor previsto: abc -> R$ 1,50"
    )
    assert frase(ev("EDICAO", "inicio_realizado", None, "ontem")) == "Início: (vazio) -> ontem"
    assert frase(ev("EDICAO", "campo_novo", "a", "b")) == "campo_novo: a -> b"
    assert frase(ev("TIPO_NOVO", "titulo", "a", "b")) == "Título alterado"
    assert frase(ev("TIPO_NOVO")) == "Campo alterado"


@pytest.mark.parametrize(
    ("dif", "pct", "esperado"),
    [
        (2000, 20.0, "+R$ 20,00 (+20,0%) - Acima do previsto"),
        (-2500, -25.0, "-R$ 25,00 (-25,0%) - Abaixo do previsto"),
        (0, 0.0, "R$ 0,00 (0,0%) - Igual ao previsto"),
        (5000, None, "+R$ 50,00 - Acima do previsto"),  # previsto zero: sem percentual
        (0, None, "R$ 0,00 - Igual ao previsto"),
        (-20000, -66.67, "-R$ 200,00 (-66,7%) - Abaixo do previsto"),
        (123456789, 1234.5, "+R$ 1.234.567,89 (+1234,5%) - Acima do previsto"),
    ],
)
def test_texto_diferenca_valor(dif, pct, esperado):
    assert texto_diferenca_valor(dif, pct) == esperado


@pytest.mark.parametrize(
    ("dif", "esperado"),
    [
        (30, "+0h30 - Acima do previsto"),
        (-15, "-0h15 - Abaixo do previsto"),
        (0, "0h00 - Igual ao previsto"),
        (125, "+2h05 - Acima do previsto"),
    ],
)
def test_texto_diferenca_tempo(dif, esperado):
    assert texto_diferenca_tempo(dif) == esperado
