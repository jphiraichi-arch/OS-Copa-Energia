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
    assert frase(ev("CRIACAO")) == "Ordem de Serviço criada"


@pytest.mark.parametrize(
    ("antigo", "novo", "esperado"),
    [
        ("ABERTA", "EM_EXECUCAO", "Status: Aberta -> Em execução"),
        ("EM_EXECUCAO", "ABERTA", "Status: Em execução -> Aberta"),
        ("EM_EXECUCAO", "CONCLUIDA", "Status: Em execução -> Concluída"),
        ("ABERTA", "CANCELADA", "Status: Aberta -> Cancelada"),
        ("ABERTA", "SUSPENSA", "Status: Aberta -> SUSPENSA"),  # status futuro: sem quebrar
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
        (
            "valor_previsto_centavos",
            "10000",
            "15000",
            "Valor previsto (legado): R$\u00a0100,00 -> R$\u00a0150,00",
        ),
        (
            "valor_previsto_centavos",
            "0",
            "123456789",
            "Valor previsto (legado): R$\u00a00,00 -> R$\u00a01.234.567,89",
        ),
        ("tempo_previsto_minutos", "60", "90", "Tempo previsto: 1h00 -> 1h30"),
        ("filial_id", "F001", "F002", "Filial: F001 -> F002"),
        (
            "valor_realizado_centavos",
            "12000",
            "9000",
            "Valor realizado (legado): R$\u00a0120,00 -> R$\u00a090,00",
        ),
        (
            "inicio_realizado",
            "2026-05-04T16:50:00+00:00",
            "2026-05-04T17:00:00+00:00",
            "Início: 04/05/2026\u00a013:50 -> 04/05/2026\u00a014:00",
        ),
        (
            "fim_realizado",
            "2026-05-04T17:30:00+00:00",
            "2026-05-05T02:10:00+00:00",
            "Fim: 04/05/2026\u00a014:30 -> 04/05/2026\u00a023:10",
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
        ("valor_realizado_centavos", "12000", "Valor realizado (legado): R$\u00a0120,00"),
        ("inicio_realizado", "2026-05-04T16:50:00+00:00", "Início: 04/05/2026\u00a013:50"),
        ("fim_realizado", "2026-05-04T17:30:00+00:00", "Fim: 04/05/2026\u00a014:30"),
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
    # Os campos antigos de preço único continuam com rótulo: aparecem no histórico de OS
    # anteriores ao prompt 13.
    assert {"status", *CAMPOS_PREVISTO, *CAMPOS_REALIZADO, CAMPO_FILIAL} <= set(historico.CAMPOS)


def test_texto_longo_e_cortado_e_quebras_de_linha_viram_espaco():
    f = frase(ev("EDICAO", "descricao", "a\nb", "x" * 300))
    assert f.startswith("Descrição: a b -> ") and f.endswith("…")
    assert len(f) < 120


def test_valores_inesperados_nao_quebram():
    assert frase(ev("EDICAO", "valor_previsto_centavos", "abc", "150")) == (
        "Valor previsto (legado): abc -> R$\u00a01,50"
    )
    # Prompt 26: vazio é '—'; campo desconhecido é 'Campo alterado' (nunca o nome cru).
    assert frase(ev("EDICAO", "inicio_realizado", None, "ontem")) == "Início: — -> ontem"
    assert frase(ev("EDICAO", "campo_novo", "a", "b")) == "Campo alterado: a -> b"
    assert frase(ev("TIPO_NOVO", "titulo", "a", "b")) == "Título: a -> b"
    assert frase(ev("TIPO_NOVO")) == "Campo alterado: — -> —"


@pytest.mark.parametrize(
    ("dif", "pct", "esperado"),
    [
        # Prompt 26: o percentual leva o sinal; o valor, não; as palavras vêm do valor.
        (2000, 20.0, "R$\u00a020,00 acima do previsto (+20%)"),
        (-2500, -25.0, "R$\u00a025,00 abaixo do previsto (\u221225%)"),
        (0, 0.0, "Igual ao previsto"),
        (5000, None, "+R$\u00a050,00 (não previsto)"),  # prompt 31: previsto zero
        (0, None, "R$\u00a00,00 — sem gasto"),  # prompt 31: nada previsto nem gasto
        (-20000, -66.67, "R$\u00a0200,00 abaixo do previsto (\u221266,7%)"),
        (123456789, 1234.5, "R$\u00a01.234.567,89 acima do previsto (+1234,5%)"),
    ],
)
def test_texto_diferenca_valor(dif, pct, esperado):
    assert texto_diferenca_valor(dif, pct) == esperado


@pytest.mark.parametrize(
    ("dif", "esperado"),
    [
        (30, "0h30 acima do previsto"),
        (-15, "0h15 abaixo do previsto"),
        (0, "Igual ao previsto"),
        (125, "2h05 acima do previsto"),
    ],
)
def test_texto_diferenca_tempo(dif, esperado):
    assert texto_diferenca_tempo(dif) == esperado


# --- Eventos de item de custo ---------------------------------------------------------


def test_item_adicionado():
    evento = ev("ITEM_ADICIONADO", "item 12", None, "Peças | Rolamento | 1,5 x R$ 33,33")
    assert frase(evento) == "Item de custo adicionado: Peças | Rolamento | 1,5 x R$ 33,33"


def test_item_alterado_diz_qual_campo_mudou():
    evento = ev("ITEM_ALTERADO", "item 12 - valor unitário", "R$ 33,33", "R$ 40,00")
    assert frase(evento) == "Item de custo alterado (valor unitário): R$ 33,33 -> R$ 40,00"
    evento = ev("ITEM_ALTERADO", "item 12 - categoria", "Peças", "Mão de obra")
    assert frase(evento) == "Item de custo alterado (categoria): Peças -> Mão de obra"


def test_item_removido():
    evento = ev("ITEM_REMOVIDO", "item 12", "Peças | Rolamento | 2 x R$ 10,00", None)
    assert frase(evento) == "Item de custo removido: Peças | Rolamento | 2 x R$ 10,00"
