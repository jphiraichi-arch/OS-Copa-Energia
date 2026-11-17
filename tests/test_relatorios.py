import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from osapp.db import sessao
from osapp.models import Usuario
from osapp.services import ordens, relatorios, relogio, status
from osapp.services.erros import ErroAutenticacao, ErroPermissao, ErroValidacao
from osapp.services.relatorios import RelatorioBasico, gerar_relatorio, limites_do_mes
from tests.fabricas import novo_usuario

MAIO = datetime(2026, 5, 20, 15, 0, tzinfo=UTC)


@pytest.fixture
def dados(cenario, monkeypatch):
    """Cenário com uma gerente em F001 e algumas OS em maio de 2026 (fuso de São Paulo)."""
    monkeypatch.setenv("OS_TZ", "America/Sao_Paulo")
    with sessao() as s:
        filial = s.get(Usuario, cenario["marina"]).filial
        cenario["gerente"] = novo_usuario(
            s, filial, "gerente.norte", "Gabriela Gerente", is_gerente=True
        ).id

    def em(instante):
        monkeypatch.setattr(relogio, "agora", lambda: instante)

    def concluida(criador, executor, previsto, realizado, minutos, quando, filial_id=None):
        em(quando - timedelta(hours=5))
        d = ordens.criar_os(criador, "Serviço de teste", "Descrição.", previsto, 60, filial_id)
        d = ordens.iniciar_execucao(executor, d.id, d.versao)
        em(quando)
        return ordens.concluir_os(
            executor,
            d.id,
            d.versao,
            realizado,
            quando - timedelta(minutes=minutos),
            quando,
            "Feito.",
        )

    c = cenario
    # F001, concluídas em maio: 3 OS
    concluida(c["marina"], c["joao"], 10000, 15000, 90, MAIO)  # +50,00
    concluida(c["marina"], c["joao"], 20000, 18000, 30, MAIO + timedelta(days=1))  # -20,00
    concluida(c["marina"], c["pedro"], 5000, 5000, 60, MAIO + timedelta(days=2))  # igual
    # F001, concluída em abril no horário local (01/05 02:00 UTC = 30/04 23:00 em São Paulo)
    concluida(c["marina"], c["joao"], 1000, 99999, 10, datetime(2026, 5, 1, 2, 0, tzinfo=UTC))
    # F001, ainda aberta e em execução (criadas em maio)
    em(MAIO)
    ordens.criar_os(c["marina"], "Aberta em maio", "Descrição.", 100, 30)
    d = ordens.criar_os(c["joao"], "Em execução", "Descrição.", 100, 30)
    ordens.iniciar_execucao(c["pedro"], d.id, d.versao)
    # F002, concluída em maio
    concluida(c["carlos"], c["carlos"], 30000, 40000, 120, MAIO)  # +100,00
    em(MAIO + timedelta(days=5))
    return c


def contagem(rel):
    return {c.status: c.total for c in rel.basico.por_status}


# --- Quem vê o quê ---------------------------------------------------------------------


def test_operario_ve_so_o_basico_da_propria_filial(dados):
    rel = gerar_relatorio(dados["marina"], 2026, 5)
    assert rel.filial_rotulo == "F001 - Filial Modelo Norte" and rel.filial_id == dados["f1"]
    assert rel.completo is None
    assert gerar_relatorio(dados["marina"], 2026, 5, dados["f1"]).completo is None
    with pytest.raises(ErroPermissao):
        gerar_relatorio(dados["marina"], 2026, 5, dados["f2"])


def test_relatorio_basico_nao_tem_dado_sensivel():
    campos = {f.name for f in dataclasses.fields(RelatorioBasico)}
    assert not {c for c in campos if "valor" in c or "centavos" in c or "executor" in c}


def test_gerente_ve_o_completo_da_propria_filial_e_nada_de_outra(dados):
    rel = gerar_relatorio(dados["gerente"], 2026, 5)
    assert rel.completo is not None and rel.filial_id == dados["f1"]
    with pytest.raises(ErroPermissao):
        gerar_relatorio(dados["gerente"], 2026, 5, dados["f2"])


def test_admin_ve_tudo(dados):
    todas = gerar_relatorio(dados["admin"], 2026, 5)
    assert todas.filial_id is None and todas.filial_rotulo == "Todas as filiais"
    assert todas.completo is not None
    assert [
        (f.filial_codigo, f.concluidas, f.valor_realizado_centavos)
        for f in todas.completo.por_filial
    ] == [("F001", 3, 38000), ("F002", 1, 40000)]
    so_f2 = gerar_relatorio(dados["admin"], 2026, 5, dados["f2"])
    assert so_f2.completo.valor_realizado_centavos == 40000
    assert so_f2.completo.por_filial == ()  # só no consolidado
    with pytest.raises(ErroValidacao):
        gerar_relatorio(dados["admin"], 2026, 5, 9999)


def test_colega_comum_e_inativo(dados):
    assert gerar_relatorio(dados["joao"], 2026, 5).completo is None
    assert gerar_relatorio(dados["carlos"], 2026, 5).filial_rotulo == "F002 - Filial Modelo Sul"
    with pytest.raises(ErroAutenticacao):
        gerar_relatorio(dados["inativa"], 2026, 5)


# --- Números ---------------------------------------------------------------------------


def test_relatorio_basico(dados):
    rel = gerar_relatorio(dados["marina"], 2026, 5)
    assert contagem(rel) == {status.ABERTA: 1, status.EM_EXECUCAO: 1, status.CONCLUIDA: 4}
    assert [c.rotulo for c in rel.basico.por_status] == ["Aberta", "Em execução", "Concluída"]
    # 6 OS em F001, mas uma foi criada em 30/04 às 18:00 no horário local: 5 em maio.
    assert rel.basico.criadas_no_mes == 5
    assert rel.basico.concluidas_no_mes == 3
    assert rel.basico.tempo_medio_execucao_minutos == 60  # (90 + 30 + 60) / 3


def test_relatorio_completo(dados):
    c = gerar_relatorio(dados["gerente"], 2026, 5).completo
    assert (c.valor_previsto_centavos, c.valor_realizado_centavos) == (35000, 38000)
    assert (c.diferenca_valor_centavos, c.diferenca_valor_percentual) == (3000, 8.57)
    assert (c.tempo_previsto_minutos, c.tempo_realizado_minutos, c.diferenca_tempo_minutos) == (
        180,
        180,
        0,
    )
    assert c.acima_do_previsto == 1
    assert [(d.valor_previsto_centavos, d.diferenca_centavos) for d in c.maiores_desvios] == [
        (10000, 5000)
    ]
    assert [
        (e.nome, e.concluidas, e.valor_realizado_centavos, e.tempo_realizado_minutos)
        for e in c.por_executor
    ] == [
        ("João Fictício", 2, 33000, 120),
        ("Pedro Modelo", 1, 5000, 60),
    ]


def test_limite_do_mes_segue_o_fuso_local(dados):
    abril = gerar_relatorio(dados["gerente"], 2026, 4)
    assert abril.basico.concluidas_no_mes == 1
    assert abril.completo.valor_realizado_centavos == 99999
    assert limites_do_mes(2026, 5, "America/Sao_Paulo") == (
        datetime(2026, 5, 1, 3, 0, tzinfo=UTC),
        datetime(2026, 6, 1, 3, 0, tzinfo=UTC),
    )
    assert limites_do_mes(2026, 12, "UTC")[1] == datetime(2027, 1, 1, tzinfo=UTC)


def test_mes_sem_movimento(dados):
    rel = gerar_relatorio(dados["admin"], 2025, 1)
    assert (rel.basico.criadas_no_mes, rel.basico.concluidas_no_mes) == (0, 0)
    assert rel.basico.tempo_medio_execucao_minutos is None
    assert rel.completo.valor_realizado_centavos == 0
    assert rel.completo.diferenca_valor_percentual is None
    assert rel.completo.maiores_desvios == () and rel.completo.por_executor == ()


def test_no_maximo_cinco_maiores_desvios(cenario, monkeypatch):
    monkeypatch.setattr(relogio, "agora", lambda: MAIO)
    for extra in range(7):
        d = ordens.criar_os(cenario["admin"], "Estouro", "Descrição.", 1000, 60)
        d = ordens.iniciar_execucao(cenario["admin"], d.id, d.versao)
        ordens.concluir_os(
            cenario["admin"],
            d.id,
            d.versao,
            2000 + extra * 100,
            MAIO - timedelta(hours=1),
            MAIO,
            "Feito.",
        )
    desvios = gerar_relatorio(cenario["admin"], 2026, 5).completo.maiores_desvios
    assert [d.diferenca_centavos for d in desvios] == [1600, 1500, 1400, 1300, 1200]


@pytest.mark.parametrize(
    ("ano", "mes", "campo"),
    [
        (1999, 5, "ano"),
        (2101, 5, "ano"),
        ("2026", 5, "ano"),
        (2026, 0, "mes"),
        (2026, 13, "mes"),
        (2026, None, "mes"),
        (2026, True, "mes"),
    ],
)
def test_validacao(cenario, ano, mes, campo):
    with pytest.raises(ErroValidacao) as info:
        gerar_relatorio(cenario["admin"], ano, mes)
    assert info.value.campo == campo


def test_filial_de_tipo_errado(cenario):
    with pytest.raises(ErroValidacao):
        gerar_relatorio(cenario["admin"], 2026, 5, "1")


def test_desativar_gerente_tira_o_acesso_na_hora(dados):
    assert relatorios.gerar_relatorio(dados["gerente"], 2026, 5).completo is not None
    with sessao() as s:
        s.get(Usuario, dados["gerente"]).ativo = False
    with pytest.raises(ErroAutenticacao):
        gerar_relatorio(dados["gerente"], 2026, 5)
