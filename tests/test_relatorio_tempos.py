"""Prompt 18: relatório de tempos de atendimento (resposta e solução)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from osapp import formatacao
from osapp.services import administracao, custos, ordens, relatorios, relogio, status
from osapp.services.erros import ErroPermissao, ErroValidacao
from tests.fabricas import NOTA, categoria_id, itens, tipo_id

SENHA = "senha-ficticia-123"
SP = ZoneInfo("America/Sao_Paulo")
H = timedelta(hours=1)
# Todas as OS do cenário são abertas no dia 10/05/2026 (horário de São Paulo).
DIA = date(2026, 5, 10)
BASE = datetime(2026, 5, 10, 8, 0, tzinfo=SP).astimezone(UTC)


class Relogio:
    def __init__(self, monkeypatch):
        self.agora = BASE
        monkeypatch.setattr(relogio, "agora", lambda: self.agora)


@pytest.fixture
def tempo(monkeypatch):
    monkeypatch.setenv("OS_TZ", "America/Sao_Paulo")
    return Relogio(monkeypatch)


@pytest.fixture
def p(banco, tempo):
    administracao.criar_filial("1007", "Jardinópolis")
    administracao.criar_filial("2001", "Outra Filial")

    def criar(nome, login, filial, papel):
        return administracao.criar_usuario(nome, login, SENHA, filial, papel=papel).id

    return {
        "sol": criar("Sônia", "sonia.sol", "1007", "usuario"),
        "man": criar("Mário", "mario.man", "1007", "manutencao"),
        "admin": criar("Ana", "ana.admin", "1007", "admin"),
        "sol_f2": criar("Paula", "paula.outra", "2001", "usuario"),
        "man_f2": criar("Otto", "otto.outra", "2001", "manutencao"),
    }


def abrir(p, tempo, aberta, urgencia="media", sol="sol", man="man"):
    """Solicitação aberta no instante ``aberta`` e completada pela manutenção."""
    tempo.agora = aberta
    v = ordens.criar_solicitacao(p[sol], "Pedido", "Descrição.", urgencia)
    d = ordens.obter_os(p[man], v.id)
    d = ordens.editar_os(
        p[man],
        d.id,
        d.versao,
        {
            "tempo_previsto_minutos": 60,
            "tipo_id": tipo_id(),
            "prioridade": "media",
        },
    )
    return custos.adicionar_item(
        p[man], d.id, d.versao, "PREVISTO", categoria_id(), "Peça", Decimal("1"), 100
    )


def iniciar(p, tempo, d, quando, man="man"):
    tempo.agora = quando
    return ordens.iniciar_execucao(p[man], d.id, d.versao)


def concluir(p, tempo, d, quando, man="man"):
    tempo.agora = quando
    return ordens.concluir_os(
        p[man], d.id, d.versao, itens(100), quando - 2 * H, quando - H, "Feito.", NOTA
    )


def solicitacao_com_tempos(p, tempo, aberta, resposta=None, solucao=None, urgencia="media"):
    d = abrir(p, tempo, aberta, urgencia)
    if resposta is not None:
        d = iniciar(p, tempo, d, aberta + resposta)
    if solucao is not None:
        d = concluir(p, tempo, d, aberta + solucao)
    return d


def relatorio(p, tempo, ator="man", **kw):
    tempo.agora = BASE + 300 * H  # o relatório é gerado bem depois de tudo
    kw.setdefault("data_inicio", DIA)
    kw.setdefault("data_fim", DIA)
    return relatorios.relatorio_tempos(p[ator], **kw)


# --- Média e mediana ---------------------------------------------------------------


def test_um_caso_extremo_puxa_a_media_e_nao_a_mediana(p, tempo):
    for n, horas in enumerate((1, 2, 3, 4, 100)):
        solicitacao_com_tempos(p, tempo, BASE + n * timedelta(minutes=1), resposta=horas * H)
    r = relatorio(p, tempo)
    assert r.resposta == relatorios.Medida(5, 22 * 3600, 3 * 3600)
    assert formatacao.formatar_tempo(r.resposta.media_segundos) == "22\u00a0h"
    assert r.solucao == relatorios.Medida(0, None, None)


def test_mediana_com_n_par(p, tempo):
    for n, horas in enumerate((1, 2, 3, 10)):
        solicitacao_com_tempos(p, tempo, BASE + n * timedelta(minutes=1), resposta=horas * H)
    r = relatorio(p, tempo)
    assert r.resposta.mediana_segundos == 2 * 3600 + 30 * 60
    assert formatacao.formatar_tempo(r.resposta.mediana_segundos) == "2\u00a0h\u00a030\u00a0min"
    assert r.resposta.media_segundos == 4 * 3600


def test_medir_arredonda_meio_para_cima():
    assert relatorios.medir([1, 2]) == relatorios.Medida(2, 2, 2)  # 1,5 -> 2
    assert relatorios.medir([]) == relatorios.Medida(0, None, None)
    assert relatorios.medir([7]) == relatorios.Medida(1, 7, 7)


# --- Quem entra e quem fica de fora ---------------------------------------------------


def test_exclusoes(p, tempo):
    valida = solicitacao_com_tempos(p, tempo, BASE, resposta=H, solucao=2 * H)
    # cancelada
    cancelada = abrir(p, tempo, BASE + H)
    ordens.cancelar(p["sol"], cancelada.id, ordens.obter_os(p["sol"], cancelada.id).versao)
    # origem manutenção
    tempo.agora = BASE
    m = ordens.criar_os(
        p["man"],
        "Preventiva",
        "Plano.",
        itens(100),
        60,
        tipo_id=tipo_id(),
        prioridade="baixa",
    )
    iniciar(p, tempo, m, BASE + H)
    # outra filial
    tempo.agora = BASE
    v = ordens.criar_solicitacao(p["sol_f2"], "Pedido", "Descrição.", "media")
    d = ordens.editar_os(
        p["man_f2"],
        v.id,
        ordens.obter_os(p["man_f2"], v.id).versao,
        {
            "tempo_previsto_minutos": 60,
            "tipo_id": tipo_id(),
            "prioridade": "media",
        },
    )
    d = custos.adicionar_item(
        p["man_f2"], d.id, d.versao, "PREVISTO", categoria_id(), "Peça", Decimal("1"), 100
    )
    iniciar(p, tempo, d, BASE + H, man="man_f2")
    # aberta fora do período (dia seguinte)
    solicitacao_com_tempos(p, tempo, BASE + 24 * H, resposta=H)

    r = relatorio(p, tempo)
    assert r.total_no_periodo == 1
    assert (r.resposta.n, r.solucao.n) == (1, 1)
    assert (r.resposta.media_segundos, r.solucao.media_segundos) == (3600, 7200)
    assert valida.numero


def test_em_execucao_conta_na_resposta_e_nao_na_solucao(p, tempo):
    solicitacao_com_tempos(p, tempo, BASE, resposta=2 * H)
    r = relatorio(p, tempo)
    assert (r.resposta.n, r.solucao.n, r.total_no_periodo) == (1, 0, 1)


def test_inicio_desfeito_nao_conta_ate_iniciar_de_novo(p, tempo):
    d = solicitacao_com_tempos(p, tempo, BASE, resposta=H)
    tempo.agora = BASE + 2 * H
    d = ordens.desfazer_inicio(p["man"], d.id, d.versao)
    r = relatorio(p, tempo)
    assert (r.resposta.n, r.solucao.n, r.total_no_periodo) == (0, 0, 1)
    iniciar(p, tempo, d, BASE + 5 * H)
    assert relatorio(p, tempo).resposta == relatorios.Medida(1, 5 * 3600, 5 * 3600)


def test_por_urgencia_inclusive_vazia(p, tempo):
    solicitacao_com_tempos(p, tempo, BASE, resposta=H, solucao=3 * H, urgencia="alta")
    solicitacao_com_tempos(p, tempo, BASE + H, resposta=3 * H, urgencia="alta")
    solicitacao_com_tempos(p, tempo, BASE + H, resposta=10 * H, urgencia="emergencial")
    r = relatorio(p, tempo)
    por = {u.urgencia: u for u in r.por_urgencia}
    assert [u.urgencia for u in r.por_urgencia] == ["baixa", "media", "alta", "emergencial"]
    assert por["baixa"].resposta == relatorios.Medida(0, None, None)
    assert por["media"].solucao == relatorios.Medida(0, None, None)
    assert por["alta"].resposta == relatorios.Medida(2, 2 * 3600, 2 * 3600)
    assert por["alta"].solucao == relatorios.Medida(1, 3 * 3600, 3 * 3600)
    assert por["emergencial"].resposta.n == 1


def test_filtro_de_status(p, tempo):
    solicitacao_com_tempos(p, tempo, BASE, resposta=H, solucao=2 * H)
    solicitacao_com_tempos(p, tempo, BASE, resposta=3 * H)
    abrir(p, tempo, BASE)
    r = relatorio(p, tempo, status=[status.EM_EXECUCAO])
    assert (r.total_no_periodo, r.resposta.n, r.solucao.n) == (1, 1, 0)
    r = relatorio(p, tempo, status=(status.CONCLUIDA, status.ABERTA))
    assert (r.total_no_periodo, r.resposta.n, r.solucao.n) == (2, 1, 1)
    for invalido in ([], ["CANCELADA"], "ABERTA", [1]):
        with pytest.raises(ErroValidacao):
            relatorio(p, tempo, status=invalido)


# --- Período em horário local -------------------------------------------------------


def test_limites_do_periodo_em_horario_local(p, tempo):
    ultimo_dia = date(2026, 5, 10)
    dentro = datetime(2026, 5, 10, 23, 30, tzinfo=SP).astimezone(UTC)
    fora = datetime(2026, 5, 11, 0, 10, tzinfo=SP).astimezone(UTC)
    solicitacao_com_tempos(p, tempo, dentro, resposta=H)
    solicitacao_com_tempos(p, tempo, fora, resposta=2 * H)
    r = relatorio(p, tempo, data_inicio=date(2026, 5, 1), data_fim=ultimo_dia)
    assert (r.total_no_periodo, r.resposta.media_segundos) == (1, 3600)
    inicio, fim = relatorios.limites_do_periodo(date(2026, 5, 1), ultimo_dia, "America/Sao_Paulo")
    assert inicio == datetime(2026, 5, 1, 3, 0, tzinfo=UTC)
    assert fim == datetime(2026, 5, 11, 3, 0, tzinfo=UTC)


def test_periodo_padrao_e_validacao(p, tempo):
    tempo.agora = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
    r = relatorios.relatorio_tempos(p["man"])
    assert (r.data_inicio, r.data_fim) == (date(2026, 5, 2), date(2026, 5, 31))  # 30 dias
    with pytest.raises(ErroValidacao):
        relatorios.relatorio_tempos(p["man"], date(2026, 5, 10), date(2026, 5, 9))
    with pytest.raises(ErroValidacao):
        relatorios.relatorio_tempos(p["man"], "2026-05-01", date(2026, 5, 9))


# --- Em aberto agora ----------------------------------------------------------------


def test_backlog_ignora_o_periodo(p, tempo):
    abrir(p, tempo, BASE - 72 * H)  # aberta 3 dias antes do período
    abrir(p, tempo, BASE)
    solicitacao_com_tempos(p, tempo, BASE, resposta=H)  # em execução: não é backlog
    r = relatorio(p, tempo)  # gerado em BASE + 300 h
    assert r.backlog.quantidade == 2
    assert r.backlog.mais_antiga_segundos == (300 + 72) * 3600
    assert formatacao.formatar_tempo(r.backlog.mais_antiga_segundos) == "15\u00a0d\u00a012\u00a0h"
    vazio = relatorio(p, tempo, ator="man_f2")
    assert vazio.backlog == relatorios.Backlog(0, None)


# --- Acesso -------------------------------------------------------------------------


def test_acesso(p, tempo):
    solicitacao_com_tempos(p, tempo, BASE, resposta=H)
    with pytest.raises(ErroPermissao):
        relatorio(p, tempo, ator="sol")
    outra = relatorio(p, tempo, ator="man_f2")
    assert (outra.total_no_periodo, outra.resposta.n, outra.filial_rotulo) == (
        0,
        0,
        "2001 - Outra Filial",
    )
    with pytest.raises(ErroPermissao):
        relatorio(p, tempo, ator="man_f2", filial_id=1)
    todas = relatorio(p, tempo, ator="admin")
    assert (todas.filial_id, todas.resposta.n) == (None, 1)
    so_2001 = relatorio(p, tempo, ator="admin", filial_id=2)
    assert so_2001.resposta.n == 0


# --- Formatação ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("segundos", "texto"),
    [
        (0, "0\u00a0min"),
        (29, "0\u00a0min"),
        (30, "1\u00a0min"),
        (45 * 60, "45\u00a0min"),
        (3600, "1\u00a0h"),
        (3 * 3600 + 20 * 60, "3\u00a0h\u00a020\u00a0min"),
        (24 * 3600, "1\u00a0d"),
        (2 * 86400 + 4 * 3600 + 59 * 60, "2\u00a0d\u00a04\u00a0h"),
    ],
)
def test_formatar_tempo(segundos, texto):
    assert formatacao.formatar_tempo(segundos) == texto


def test_formatar_tempo_recusa_negativo_e_tipo_errado():
    with pytest.raises(ValueError):
        formatacao.formatar_tempo(-1)
    with pytest.raises(TypeError):
        formatacao.formatar_tempo(1.5)
