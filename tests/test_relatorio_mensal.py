"""Prompt 25: relatório mensal (mês selecionado e acumulado) com status refeito pelos
eventos. Relógio trocado e instantes fixos; os valores esperados foram calculados à mão
a partir dos dados abaixo (horário de São Paulo, UTC-3 em 2026).

Outubro (todas na 1007):
  A 05/10 08:00 'Balança' 1000; início 05/10 10:00 (2 h); conclusão 06/10 08:00 (24 h),
    realizado 1500
  B 10/10 08:00 'Motor' 2000; início 10/10 09:00 (1 h)
  C 12/10 08:00 'Balança' 500; cancelada 13/10 08:00
  D 31/10 23:30 'Balança' 700 (já é 01/11 em UTC, mas é outubro)
  E 20/10 08:00 'Motor' 3000; início 20/10 12:00 (4 h); desfeito 05/11; novo início
    10/11 08:00; conclusão 02/12 08:00
  F 15/10 08:00 'Balança' 400; início 15/10 09:00 (1 h); conclusão 02/11 09:00 (433 h)
Novembro:
  G 01/11 00:10 'Balança' 1000; início 01/11 02:10 (2 h); conclusão 03/11 00:10 (48 h),
    realizado 3000
  H 15/11 08:00 'Correia' 900; excluída em 16/11 (nunca conta)
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from osapp import cli
from osapp.db import sessao
from osapp.models import OrdemServico
from osapp.services import administracao, custos, lixeira, ordens, relatorios
from osapp.services.erros import ErroPermissao, ErroValidacao
from osapp.services.linha_do_tempo import Marco, periodo_do_mes, situacao_em, status_em
from osapp.ui.views.relatorio_tempos import texto_taxa
from tests.fabricas import categoria_id, especialidade_id, motivo_id, tipo_id
from tests.test_relatorio_tempos import SENHA, Relogio

SP = ZoneInfo("America/Sao_Paulo")
H = 3600


def local(dia: int, mes: int, hora: int = 8, minuto: int = 0, ano: int = 2026) -> datetime:
    return datetime(ano, mes, dia, hora, minuto, tzinfo=SP)


@pytest.fixture
def tempo(monkeypatch):
    monkeypatch.setenv("OS_TZ", "America/Sao_Paulo")
    return Relogio(monkeypatch)


@pytest.fixture
def p(banco, tempo):
    administracao.criar_filial("1007", "Jardinópolis")

    def criar(nome, login, papel):
        return administracao.criar_usuario(nome, login, SENHA, "1007", papel=papel).id

    return {
        "sol": criar("Sônia", "sonia.sol", "usuario"),
        "man": criar("Mário", "mario.man", "manutencao"),
        "admin": criar("Ana", "ana.admin", "admin"),
    }


class Cenario:
    def __init__(self, p, tempo):
        self.p, self.tempo = p, tempo

    def em(self, quando):
        self.tempo.agora = quando.astimezone(UTC)

    def nova(self, quando, titulo, item, valor):
        self.em(quando)
        v = ordens.criar_solicitacao(self.p["sol"], titulo, "Pedido.", "media")
        d = ordens.obter_os(self.p["man"], v.id)
        d = ordens.editar_os(
            self.p["man"],
            d.id,
            d.versao,
            {
                "tempo_previsto_minutos": 60,
                "tipo_id": tipo_id(),
                "especialidade_id": especialidade_id(),
            },
        )
        return custos.adicionar_item(
            self.p["man"], d.id, d.versao, "PREVISTO", categoria_id(), item, Decimal("1"), valor
        )

    def _atual(self, d):
        return ordens.obter_os(self.p["admin"], d.id)

    def iniciar(self, d, quando):
        self.em(quando)
        return ordens.iniciar_execucao(self.p["man"], d.id, self._atual(d).versao)

    def desfazer(self, d, quando):
        self.em(quando)
        return ordens.desfazer_inicio(self.p["man"], d.id, self._atual(d).versao)

    def concluir(self, d, quando, realizado=100):
        self.em(quando)
        fim = quando.astimezone(UTC) - timedelta(hours=1)
        return ordens.concluir_os(
            self.p["man"],
            d.id,
            self._atual(d).versao,
            [custos.ItemEntrada(categoria_id(), "Mão de obra", Decimal("1"), realizado)],
            fim - timedelta(hours=1),
            fim,
            "Feito.",
            "Pronto.",
        )

    def cancelar(self, d, quando):
        self.em(quando)
        return ordens.cancelar(self.p["admin"], d.id, self._atual(d).versao, motivo_id())


def sem_agora(r):
    """O relatório sem o cartão 'Solicitações em aberto', que é a situação de agora (não
    do período) e por isso muda com o tempo."""
    return replace(r, backlog=None)


def rel(p, mes, termo=None, **kw):
    return relatorios.relatorio_mensal(p["man"], 2026, mes, termo, **kw)


@pytest.fixture
def dados(p, tempo):
    """Monta o cenário em ordem cronológica e guarda relatórios intermediários."""
    c = Cenario(p, tempo)
    o = {}
    o["A"] = c.nova(local(5, 10), "Pedido A", "Balança", 1000)
    c.iniciar(o["A"], local(5, 10, 10))
    c.concluir(o["A"], local(6, 10), realizado=1500)
    o["B"] = c.nova(local(10, 10), "Pedido B", "Motor", 2000)
    c.iniciar(o["B"], local(10, 10, 9))
    o["C"] = c.nova(local(12, 10), "Pedido C", "Balança", 500)
    c.cancelar(o["C"], local(13, 10))
    o["F"] = c.nova(local(15, 10), "Pedido F", "Balança", 400)
    c.iniciar(o["F"], local(15, 10, 9))
    o["E"] = c.nova(local(20, 10), "Pedido E", "Motor", 3000)
    c.iniciar(o["E"], local(20, 10, 12))
    o["D"] = c.nova(local(31, 10, 23, 30), "Pedido D", "Balança", 700)
    o["G"] = c.nova(local(1, 11, 0, 10), "Pedido G", "Balança", 1000)
    c.iniciar(o["G"], local(1, 11, 2, 10))
    c.concluir(o["F"], local(2, 11, 9))
    c.concluir(o["G"], local(3, 11, 0, 10), realizado=3000)
    c.desfazer(o["E"], local(5, 11))
    c.em(local(6, 11))
    intermediarios = {"outubro_06_11": rel(p, 10)}
    c.iniciar(o["E"], local(10, 11))
    c.em(local(11, 11))
    intermediarios["outubro_11_11"] = rel(p, 10)
    o["H"] = c.nova(local(15, 11), "Pedido H", "Correia", 900)
    c.em(local(16, 11))
    lixeira.excluir_os(
        p["admin"],
        o["H"].id,
        ordens.obter_os(p["admin"], o["H"].id).versao,
        "Aberta por engano no sistema.",
    )
    c.em(local(30, 11, 12))
    intermediarios["novembro_30_11"] = rel(p, 11)
    c.concluir(o["E"], local(2, 12))
    c.em(local(20, 12))
    return {"o": o, "p": p, "c": c, **intermediarios}


# --- Funções puras -------------------------------------------------------------------


def test_periodo_do_mes_no_fuso_local():
    inicio, fim = periodo_do_mes(2026, 10, "America/Sao_Paulo")
    assert inicio == datetime(2026, 10, 1, 3, tzinfo=UTC)
    assert fim == datetime(2026, 11, 1, 3, tzinfo=UTC)
    assert periodo_do_mes(2026, 12, "America/Sao_Paulo")[1] == datetime(2027, 1, 1, 3, tzinfo=UTC)


def test_status_em_usa_a_ultima_transicao_antes_de_t():
    t = [datetime(2026, 10, d, tzinfo=UTC) for d in range(1, 8)]
    eventos = [
        Marco(t[0], "CRIACAO"),
        Marco(t[1], "EDICAO", "qualquer"),  # ignorado
        Marco(t[2], "STATUS", "EM_EXECUCAO"),
        Marco(t[3], "STATUS", "ABERTA"),  # desfazer início
        Marco(t[4], "STATUS", "EM_EXECUCAO"),
        Marco(t[5], "STATUS", "CONCLUIDA"),
    ]
    assert status_em(eventos, t[0]) is None  # antes de existir (fim exclusivo)
    assert status_em(eventos, t[1]) == "ABERTA"
    assert status_em(eventos, t[3]) == "EM_EXECUCAO"
    assert status_em(eventos, t[4]) == "ABERTA"
    assert status_em(eventos, t[6]) == "CONCLUIDA"
    assert situacao_em(eventos, t[4]).inicio is None  # desfeito antes de t
    s = situacao_em(eventos, t[6])
    assert (s.inicio, s.concluida_em) == (t[4], t[5])  # o início que valeu
    assert status_em(list(reversed(eventos)), t[6]) == "CONCLUIDA"  # a ordem não importa


@pytest.mark.parametrize(
    ("concluidas", "abertas", "canceladas", "texto"),
    [(34, 40, 6, "100% (34 de 34)"), (34, 40, 0, "85% (34 de 40)"), (0, 3, 3, "—"), (0, 0, 0, "—")],
)
def test_taxa_de_conclusao(concluidas, abertas, canceladas, texto):
    taxa = relatorios.taxa_de_conclusao(concluidas, abertas, canceladas)
    assert taxa.denominador == abertas - canceladas
    assert texto_taxa(taxa) == texto


# --- Relatório com dados ----------------------------------------------------------------


def test_outubro_conferido_a_mao(dados):
    r = rel(dados["p"], 10)
    m = r.mes_selecionado
    assert (m.fluxo.abertas, m.fluxo.concluidas, m.fluxo.canceladas) == (6, 1, 1)
    assert (m.taxa.numerador, m.taxa.denominador, m.taxa.percentual) == (1, 5, 20.0)
    # Resposta: A 2 h, B 1 h, E 4 h (início de 20/10), F 1 h -> média 2 h, mediana 1,5 h.
    assert (m.resposta.n, m.resposta.media_segundos, m.resposta.mediana_segundos) == (
        4,
        2 * H,
        5400,
    )
    assert (m.solucao.n, m.solucao.media_segundos) == (1, 24 * H)
    assert m.custos.previsto_total_centavos == 1000 + 2000 + 700 + 3000 + 400
    assert (m.custos.concluidas, m.custos.previsto_concluidas_centavos) == (1, 1000)
    assert m.custos.realizado_concluidas_centavos == 1500
    # O acumulado até o fim de outubro é o próprio outubro (não há nada antes).
    a = r.acumulado
    assert (a.fluxo, a.taxa, a.resposta, a.solucao) == (m.fluxo, m.taxa, m.resposta, m.solucao)
    # Lista do mês: as abertas em outubro com status no fim de outubro (C cancelada fica fora).
    o = dados["o"]
    assert [x.os_id for x in r.ordens] == [o[k].id for k in ("D", "E", "F", "B", "A")]
    assert {x.os_id: x.status for x in r.ordens}[o["F"].id] == "EM_EXECUCAO"  # não CONCLUIDA


def test_novembro_e_acumulado_conferidos_a_mao(dados):
    r = rel(dados["p"], 11)
    m = r.mes_selecionado
    # Abertas: só G (H foi excluída). Concluídas em novembro: F (aberta em outubro) e G.
    assert (m.fluxo.abertas, m.fluxo.concluidas, m.fluxo.canceladas) == (1, 2, 0)
    assert (m.taxa.numerador, m.taxa.denominador, m.taxa.percentual) == (1, 1, 100.0)
    assert (m.resposta.n, m.resposta.media_segundos) == (1, 2 * H)
    assert (m.solucao.n, m.solucao.media_segundos) == (1, 48 * H)
    a = r.acumulado
    assert (a.fluxo.abertas, a.fluxo.concluidas, a.fluxo.canceladas) == (7, 3, 1)
    assert (a.taxa.numerador, a.taxa.denominador, a.taxa.percentual) == (3, 6, 50.0)
    # Resposta no fim de novembro: A 2, B 1, E 504 (o novo início, de 10/11), F 1, G 2 (h).
    assert (a.resposta.n, a.resposta.media_segundos, a.resposta.mediana_segundos) == (
        5,
        102 * H,
        2 * H,
    )
    # Solução: A 24, F 433, G 48 (h) -> média 168h20 = 606000 s, mediana 48 h.
    assert (a.solucao.n, a.solucao.media_segundos, a.solucao.mediana_segundos) == (
        3,
        606000,
        48 * H,
    )
    # A conclusão de E em dezembro não muda novembro (relatório tirado em 30/11).
    assert sem_agora(r) == sem_agora(dados["novembro_30_11"])


def test_conclusao_em_novembro_nao_conta_em_outubro(dados):
    outubro, novembro = rel(dados["p"], 10), rel(dados["p"], 11)
    # F foi aberta em outubro e concluída em 02/11: conta só no fluxo de novembro, e no
    # fim de outubro ainda não estava concluída (a taxa de outubro não a conta).
    assert outubro.mes_selecionado.fluxo.concluidas == 1
    assert novembro.mes_selecionado.fluxo.concluidas == 2
    assert outubro.mes_selecionado.taxa.numerador == 1


def test_desfazer_e_reiniciar_nao_mudam_outubro(dados):
    """E: iniciada 20/10, desfeita 05/11, iniciada de novo 10/11, concluída 02/12. No fim
    de outubro estava Em execução, com o início de 20/10; outubro recalculado depois de
    10/11 (e depois de dezembro) dá os mesmos números."""
    agora = rel(dados["p"], 10)
    assert (
        sem_agora(agora) == sem_agora(dados["outubro_06_11"]) == sem_agora(dados["outubro_11_11"])
    )
    status_e = {x.os_id: x.status for x in agora.ordens}[dados["o"]["E"].id]
    assert status_e == "EM_EXECUCAO"
    # As colunas mudaram depois do fato (inicio_execucao_em é o de 10/11)...
    with sessao() as s:
        assert s.get(OrdemServico, dados["o"]["E"].id).inicio_execucao_em == local(10, 11)
    # ...mas outubro usa o início de 20/10 (4 h depois da abertura).
    assert agora.mes_selecionado.resposta.n == 4


def test_excluida_nunca_conta(dados):
    for mes in (10, 11):
        r = rel(dados["p"], mes)
        ids = {x.os_id for x in r.ordens}
        assert dados["o"]["H"].id not in ids
    assert rel(dados["p"], 11).acumulado.fluxo.abertas == 7  # A..G, sem H


def test_busca_no_mes_e_no_acumulado(dados):
    """'balanca' casa A, C, D, F e G (H nem existe mais). Contas feitas à mão."""
    outubro = rel(dados["p"], 10, "balanca")
    m = outubro.mes_selecionado
    assert (m.fluxo.abertas, m.fluxo.concluidas, m.fluxo.canceladas) == (4, 1, 1)
    assert (m.taxa.numerador, m.taxa.denominador, m.taxa.percentual) == (1, 3, 33.33)
    assert (m.resposta.n, m.resposta.media_segundos, m.resposta.mediana_segundos) == (
        2,
        5400,
        5400,
    )
    assert (m.busca.correspondentes, m.busca.total, m.busca.percentual) == (3, 5, 60.0)
    assert m.custos.previsto_total_centavos == 1000 + 700 + 400
    assert (m.custos.previsto_concluidas_centavos, m.custos.realizado_concluidas_centavos) == (
        1000,
        1500,
    )
    novembro = rel(dados["p"], 11, "BALANÇA")
    a = novembro.acumulado
    assert (a.fluxo.abertas, a.fluxo.concluidas, a.fluxo.canceladas) == (5, 3, 1)
    assert (a.taxa.numerador, a.taxa.denominador, a.taxa.percentual) == (3, 4, 75.0)
    assert (a.resposta.n, a.resposta.media_segundos, a.resposta.mediana_segundos) == (
        3,
        6000,
        2 * H,
    )
    assert (a.solucao.n, a.solucao.media_segundos) == (3, 606000)
    assert (a.busca.correspondentes, a.busca.total) == (4, 6)
    assert novembro.mes_selecionado.busca.correspondentes == 1


def test_filtro_de_status_no_fim_do_periodo(dados):
    so_concluidas = rel(dados["p"], 10, status=("CONCLUIDA",))
    assert [x.os_id for x in so_concluidas.ordens] == [dados["o"]["A"].id]
    assert so_concluidas.mes_selecionado.fluxo.abertas == 6  # o fluxo não usa o filtro


def test_limites_do_mes_em_horario_local(p, tempo):
    c = Cenario(p, tempo)
    outubro = c.nova(local(31, 10, 23, 30), "Fim de outubro", "Peça", 100)
    novembro = c.nova(local(1, 11, 0, 10), "Começo de novembro", "Peça", 100)
    assert outubro.aberta_em.month == 11  # em UTC já é novembro
    c.em(local(20, 11))
    assert [x.os_id for x in rel(p, 10).ordens] == [outubro.id]
    assert [x.os_id for x in rel(p, 11).ordens] == [novembro.id]


def test_usuario_recusado_e_mes_futuro(p, tempo):
    tempo.agora = local(20, 11).astimezone(UTC)
    with pytest.raises(ErroPermissao):
        relatorios.relatorio_mensal(p["sol"], 2026, 11)
    with pytest.raises(ErroValidacao):
        relatorios.relatorio_mensal(p["man"], 2026, 12)
    assert relatorios.relatorio_mensal(p["man"], 2026, 11).mes_selecionado.fluxo.abertas == 0


# --- Conferência do histórico --------------------------------------------------------


def test_verificar_eventos_status(dados, capsys):
    assert administracao.verificar_eventos_status() == []
    assert cli.main(["verificar-eventos-status"]) == 0
    assert "Nenhuma divergência" in capsys.readouterr().out
    from osapp import db

    tabela = OrdemServico.__table__
    with db.obter_engine().begin() as conexao:
        conexao.execute(
            tabela.update().where(tabela.c.id == dados["o"]["B"].id).values(status="CONCLUIDA")
        )
    achados = administracao.verificar_eventos_status()
    assert [a.numero for a in achados] == [dados["o"]["B"].numero]
    assert "pelos eventos EM_EXECUCAO" in achados[0].problema
