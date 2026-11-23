"""Prompt 26: valores numa linha só, textos de diferença, rótulos do histórico e a
decisão tabela/cartões da tabela de custos."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from osapp import formatacao
from osapp.formatacao import MENOS, NBSP
from osapp.services import custos, ordens
from osapp.ui import historico, rotulos_eventos, tabela_custos, theme
from tests.conftest import RAIZ

# --- Formatadores ---------------------------------------------------------------------

VALORES = [
    formatacao.formatar_brl(9_999_999_999),
    formatacao.formatar_brl(-123456),
    formatacao.formatar_brl(0),
    formatacao.formatar_duracao(999 * 60 + 59),
    formatacao.formatar_tempo(3 * 86400 + 4 * 3600),
    formatacao.formatar_tempo(3 * 3600 + 20 * 60),
    formatacao.formatar_tempo(45 * 60),
    formatacao.formatar_data_hora(datetime(2026, 11, 23, 15, 5, tzinfo=UTC), "UTC"),
    formatacao.formatar_percentual(100),
    formatacao.formatar_percentual(-12.5, sinal=True),
]


@pytest.mark.parametrize("valor", VALORES)
def test_nenhum_valor_tem_espaco_comum(valor):
    assert " " not in valor


def test_extremos():
    assert formatacao.formatar_brl(9_999_999_999) == f"R${NBSP}99.999.999,99"
    assert formatacao.formatar_duracao(999 * 60 + 59) == "999h59"
    assert formatacao.formatar_duracao(178) == "2h58"
    assert formatacao.formatar_percentual(100) == "100%"
    assert formatacao.formatar_percentual(12.5) == "12,5%"
    assert formatacao.formatar_percentual(33.333) == "33,3%"
    assert formatacao.formatar_percentual(12, sinal=True) == "+12%"
    assert formatacao.formatar_percentual(-12, sinal=True) == f"{MENOS}12%"
    assert formatacao.formatar_percentual(0, sinal=True) == "0%"
    assert formatacao.formatar_tempo(3 * 3600 + 20 * 60) == f"3{NBSP}h{NBSP}20{NBSP}min"
    assert (
        formatacao.formatar_data_hora(datetime(2026, 11, 23, 15, 5, tzinfo=UTC), "UTC")
        == f"23/11/2026{NBSP}15:05"
    )
    assert formatacao.ler_brl(formatacao.formatar_brl(123456)) == 123456  # ida e volta


# --- Textos de diferença -------------------------------------------------------------


@pytest.mark.parametrize(
    ("minutos", "esperado"),
    [
        (178, "2h58 acima do previsto"),
        (-178, "2h58 abaixo do previsto"),
        (0, "Igual ao previsto"),
        (-(999 * 60 + 59), "999h59 abaixo do previsto"),
    ],
)
def test_diferenca_de_tempo(minutos, esperado):
    assert historico.texto_diferenca_tempo(minutos) == esperado


@pytest.mark.parametrize(
    ("centavos", "pct", "esperado"),
    [
        (12000, 12.0, f"R${NBSP}120,00 acima do previsto (+12%)"),
        (-12000, -12.0, f"R${NBSP}120,00 abaixo do previsto ({MENOS}12%)"),
        (0, 0.0, "Igual ao previsto"),
        (0, None, "Igual ao previsto"),
        (5000, None, f"R${NBSP}50,00 acima do previsto"),  # previsto 0: sem percentual
        (-9_999_999_999, -100.0, f"R${NBSP}99.999.999,99 abaixo do previsto ({MENOS}100%)"),
    ],
)
def test_diferenca_de_valor(centavos, pct, esperado):
    assert historico.texto_diferenca_valor(centavos, pct) == esperado


def test_diferenca_compacta_das_categorias():
    assert historico.texto_diferenca_compacta(12000, 12.0) == f"+R${NBSP}120,00 (+12%)"
    assert historico.texto_diferenca_compacta(-12000, -12.0) == (
        f"{MENOS}R${NBSP}120,00 ({MENOS}12%)"
    )
    assert historico.texto_diferenca_compacta(0, 0.0) == f"R${NBSP}0,00"
    assert historico.texto_diferenca_compacta(500, None) == f"+R${NBSP}5,00"
    assert historico.etiqueta_diferenca(1) == "acima"
    assert historico.etiqueta_diferenca(-1) == "abaixo"
    assert historico.etiqueta_diferenca(0) is None


@pytest.mark.parametrize("centavos", [-100000, -1, 0, 1, 100000])
@pytest.mark.parametrize("pct", [None, -50.0, 0.0, 50.0])
def test_nunca_sinal_de_menos_com_as_palavras(centavos, pct):
    for texto in (
        historico.texto_diferenca_valor(centavos, pct),
        historico.texto_diferenca_tempo(centavos),
    ):
        palavras = "abaixo" in texto or "acima" in texto
        valor = texto.split(" (")[0]  # o percentual pode ter sinal; o valor, não
        assert not (palavras and ("-" in valor or MENOS in valor)), texto


# --- Rótulos do histórico ------------------------------------------------------------


def _campos_gravados_no_codigo() -> set[str]:
    """Todo campo que o código atual grava em os_eventos."""
    campos = {
        *ordens.CAMPOS_TEXTO,
        *ordens.CAMPOS_MANUTENCAO,
        *ordens.CAMPOS_SOLICITACAO,
        *ordens.CAMPOS_REALIZADO,
        ordens.CAMPO_FILIAL,
        "nota_conclusao",
    }
    texto = "\n".join(
        p.read_text(encoding="utf-8") for p in (RAIZ / "src" / "osapp" / "services").glob("*.py")
    )
    # registrar_evento(..., TIPO_X, agora, "campo", ...) e o evento de status.
    campos.update(re.findall(r"TIPO_[A-Z]+,\s*\w+,\s*\"([a-z_]+)\"", texto))
    return campos


def test_todo_campo_gravado_tem_rotulo():
    campos = _campos_gravados_no_codigo()
    assert {"status", "origem", "exclusao", "prioridade"} <= campos
    sem = [c for c in campos if not rotulos_eventos.tem_rotulo(c)]
    assert sem == []
    for campo in campos:
        assert rotulos_eventos.rotulo(campo) != rotulos_eventos.CAMPO_DESCONHECIDO


def test_campos_legados_tem_rotulo():
    r = rotulos_eventos.rotulo
    assert r("equipamento_id") == r("equipamento_outro") == "Equipamento (legado)"
    assert r("valor_previsto_centavos") == "Valor previsto (legado)"
    assert r("valor_realizado_centavos") == "Valor realizado (legado)"
    assert rotulos_eventos.formatar("equipamento_id", "3") == "Equipamento nº 3 (legado)"
    assert rotulos_eventos.formatar("valor_previsto_centavos", "12000") == f"R${NBSP}120,00"
    assert r("item 12") == r("item 12 - valor unitário") == "Item de custo"


@pytest.mark.parametrize(
    ("campo", "valor", "esperado"),
    [
        ("tempo_previsto_minutos", "90", "1h30"),
        ("inicio_realizado", "2026-11-23T18:05:00+00:00", f"23/11/2026{NBSP}15:05"),
        ("status", "EM_EXECUCAO", "Em execução"),
        ("urgencia", "emergencial", "Emergencial"),
        ("prioridade", "media", "Média"),
        ("origem", "solicitacao", "Solicitação"),
        ("titulo", None, "—"),
        ("titulo", "", "—"),
        ("tempo_previsto_minutos", "não é número", "não é número"),
    ],
)
def test_valores_formatados_pelo_tipo(campo, valor, esperado, monkeypatch):
    monkeypatch.setenv("OS_TZ", "America/Sao_Paulo")
    assert rotulos_eventos.formatar(campo, valor) == esperado


@dataclass
class Evento:
    tipo: str
    campo: str | None
    valor_antigo: str | None
    valor_novo: str | None
    observacao: str | None = None


def test_campo_desconhecido_vira_campo_alterado_e_avisa_no_log(caplog):
    evento = Evento("EDICAO", "coluna_misteriosa_x", "a", "b")
    with caplog.at_level(logging.WARNING, logger="osapp.ui.rotulos_eventos"):
        frase = historico.frase(evento)
    assert frase == "Campo alterado: a -> b"
    assert "coluna_misteriosa_x" not in frase
    assert any("coluna_misteriosa_x" in r.getMessage() for r in caplog.records)
    assert "coluna_misteriosa_x" not in historico.frase(
        Evento("OUTRO", "coluna_misteriosa_x", None, None)
    )


def test_cli_verificar_rotulos_eventos(banco, capsys):
    from osapp import cli
    from osapp.db import sessao
    from osapp.models import OsEvento
    from tests.fabricas import nova_filial, nova_os, novo_usuario

    with sessao() as s:
        f = nova_filial(s)
        u = novo_usuario(s, f)
        o = nova_os(s, f, u)
        s.add(OsEvento(os_id=o.id, usuario_id=u.id, tipo="EDICAO", campo="titulo"))
        s.add(OsEvento(os_id=o.id, usuario_id=u.id, tipo="EDICAO", campo="item 3"))
    assert cli.main(["verificar-rotulos-eventos"]) == 0
    assert "Todos os campos" in capsys.readouterr().out
    with sessao() as s:
        s.add(OsEvento(os_id=o.id, usuario_id=u.id, tipo="EDICAO", campo="campo_novo"))
    cli.main(["verificar-rotulos-eventos"])
    saida = capsys.readouterr().out
    assert "campo_novo" in saida and "1 campo(s) sem rótulo" in saida


# --- Tabela de custos ------------------------------------------------------------------


def test_tabela_ou_cartoes_pela_largura():
    assert tabela_custos.LARGURA_MIN_TABELA == theme.LARGURA_CELULAR_MAX
    assert tabela_custos.modo(599) == "cartoes"
    assert tabela_custos.modo(360) == "cartoes"
    assert tabela_custos.modo(None) == "cartoes"
    assert tabela_custos.modo(600) == "tabela"
    assert tabela_custos.modo(1280) == "tabela"
    assert sum(tabela_custos.PROPORCOES) == 10 and tabela_custos.PROPORCOES[0] == 4


def _resumo():
    @dataclass
    class Item:
        fase: str
        categoria_id: int
        categoria_nome: str
        categoria_ordem: int
        quantidade: object
        valor_unitario_centavos: int

    from decimal import Decimal

    return custos.calcular_resumo(
        [
            Item("PREVISTO", 1, "Peças", 1, Decimal(1), 100000),
            Item("REALIZADO", 1, "Peças", 1, Decimal(1), 112000),
            Item("PREVISTO", 2, "Mão de obra com nome muito comprido", 2, Decimal(1), 50000),
            Item("REALIZADO", 2, "Mão de obra com nome muito comprido", 2, Decimal(1), 40000),
        ]
    )


def test_linhas_da_tabela_palavras_so_no_total():
    linhas = tabela_custos.linhas(_resumo(), com_realizado=True)
    assert [x.nome for x in linhas] == ["Peças", "Mão de obra com nome muito comprido", "Total"]
    pecas, mao, total = linhas
    # Categoria: o valor e o percentual ('+R$ 120,00 (+12%)'), cada um numa linha só.
    assert (pecas.diferenca, pecas.percentual) == (f"+R${NBSP}120,00", "(+12%)")
    assert pecas.etiqueta == "acima"
    assert (mao.diferenca, mao.percentual) == (f"{MENOS}R${NBSP}100,00", f"({MENOS}20%)")
    assert mao.etiqueta == "abaixo"
    assert total.total and total.etiqueta is None
    assert total.diferenca == f"R${NBSP}20,00 acima do previsto (+1,3%)"
    for linha in linhas[:-1]:
        assert "previsto" not in linha.diferenca.lower()
    sem = tabela_custos.linhas(_resumo(), com_realizado=False)
    assert all(x.realizado == x.diferenca == "—" for x in sem)
