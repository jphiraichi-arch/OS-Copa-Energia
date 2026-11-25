"""Prompt 38: SLA por filial e urgência, prazos na OS, etiqueta e % no relatório."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import MetaData, select

from osapp import db
from osapp.services import administracao, custos, ordens, relatorios, relogio, sla
from osapp.services.erros import ErroPermissao, ErroValidacao
from tests.conftest import config_alembic
from tests.fabricas import categoria_id, especialidade_id, tipo_id

SENHA = "senha-ficticia-123"
# 10/11/2026 10:00 em Brasília.
T0 = datetime(2026, 11, 10, 13, 0, tzinfo=UTC)
H = timedelta(hours=1)


class Relogio:
    def __init__(self):
        self.agora = T0

    def __call__(self):
        return self.agora


@pytest.fixture
def p(banco, monkeypatch):
    r = Relogio()
    monkeypatch.setattr(relogio, "agora", r)
    f = administracao.criar_filial("1007", "Jardinópolis")

    def criar(nome, login, papel):
        return administracao.criar_usuario(nome, login, SENHA, "1007", papel=papel).id

    return {
        "r": r,
        "f": f.id,
        "admin": criar("Ana Admin", "ana.admin", "admin"),
        "man": criar("Mário", "mario.man", "manutencao"),
        "sol": criar("Sônia", "sonia.sol", "usuario"),
    }


def _abrir(p, urgencia="alta", quando=None, titulo="Bomba"):
    if quando is not None:
        p["r"].agora = quando
    v = ordens.criar_solicitacao(p["sol"], titulo, "Descrição.", urgencia)
    return ordens.obter_os(p["man"], v.id)


def _iniciar(p, d, quando):
    p["r"].agora = quando
    d = ordens.obter_os(p["man"], d.id)
    d = ordens.editar_os(
        p["man"],
        d.id,
        d.versao,
        {
            "tempo_previsto_minutos": 60,
            "tipo_id": tipo_id(),
            "especialidade_id": especialidade_id(),
            "prioridade": "media",
        },
    )
    d = custos.adicionar_item(
        p["man"], d.id, d.versao, "PREVISTO", categoria_id(), "Peça", Decimal("1"), 1000
    )
    return ordens.iniciar_execucao(p["man"], d.id, d.versao)


def _concluir(p, d, quando):
    p["r"].agora = quando
    d = ordens.obter_os(p["man"], d.id)
    return ordens.concluir_os(
        p["man"],
        d.id,
        d.versao,
        [custos.ItemEntrada(categoria_id(), "Peça", Decimal("1"), 1000)],
        quando - H,
        quando,
        "Feito.",
        "Serviço feito conforme o previsto.",
    )


# --- Prazos ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("urgencia", "inicio", "solucao"),
    [
        ("emergencial", H, 8 * H),
        ("alta", 4 * H, 48 * H),
        ("media", 24 * H, 5 * 24 * H),
        ("baixa", 3 * 24 * H, 15 * 24 * H),
    ],
)
def test_prazos_pelos_padroes(p, urgencia, inicio, solucao):
    d = _abrir(p, urgencia)
    assert d.prazo_inicio_em == T0 + inicio and d.prazo_solucao_em == T0 + solucao


def test_mudar_urgencia_aberta_recalcula_com_evento(p):
    d = _abrir(p, "baixa")
    p["r"].agora = T0 + H
    ordens.editar_solicitacao(p["sol"], d.id, d.versao, {"urgencia": "emergencial"})
    d = ordens.obter_os(p["man"], d.id)
    assert d.prazo_inicio_em == T0 + H and d.prazo_solucao_em == T0 + 8 * H  # desde a abertura
    campos = {e.campo for e in ordens.listar_eventos(p["man"], d.id)}
    assert {"prazo_inicio_em", "prazo_solucao_em"} <= campos


def test_mudar_alvos_depois_nao_muda_ordens_existentes(p):
    d = _abrir(p, "alta")
    sla.definir_alvo(p["admin"], p["f"], "alta", 30, 600)
    assert ordens.obter_os(p["man"], d.id).prazo_inicio_em == T0 + 4 * H
    nova = _abrir(p, "alta", titulo="Depois")
    assert nova.prazo_inicio_em == T0 + timedelta(minutes=30)
    assert nova.prazo_solucao_em == T0 + timedelta(minutes=600)


def test_filial_nova_recebe_os_padroes(p):
    f2 = administracao.criar_filial("2001", "Outra")
    alvos = {a.filial_codigo: a for a in sla.listar_alvos(p["admin"])}
    assert [(x.urgencia, x.prazo_inicio_min, x.prazo_solucao_min) for x in alvos["2001"].alvos] == [
        ("emergencial", 60, 480),
        ("alta", 240, 2880),
        ("media", 1440, 7200),
        ("baixa", 4320, 21600),
    ]
    assert f2.codigo == "2001"


def test_os_sem_urgencia_nao_tem_prazo_nem_etiqueta(p):
    d = ordens.criar_os(p["man"], "OS da manutenção", "Descrição.", [])
    assert d.prazo_inicio_em is None and d.sla is None


# --- Etiquetas ---------------------------------------------------------------------------


def test_etiquetas_ao_longo_do_tempo(p):
    d = _abrir(p, "alta")  # início em 4 h, solução em 48 h
    assert d.sla.texto == "No prazo" and d.sla.codigo == sla.NO_PRAZO
    p["r"].agora = T0 + timedelta(hours=3, minutes=12)  # 80% do prazo de início
    d = ordens.obter_os(p["man"], d.id)
    assert d.sla.codigo == sla.VENCE and d.sla.texto == "Vence em 48 min"
    p["r"].agora = T0 + timedelta(hours=4, minutes=1)
    assert ordens.obter_os(p["man"], d.id).sla.texto == "Atrasada"
    # Ao iniciar, vale o prazo de solução.
    d = _iniciar(p, d, T0 + timedelta(hours=5))
    assert d.sla.texto == "No prazo"
    p["r"].agora = T0 + 40 * H  # faltam 8 h de 48 (16,7%)
    assert ordens.obter_os(p["man"], d.id).sla.texto == "Vence em 8 h"
    itens = ordens.listar_os(p["man"]).itens
    assert itens[0].sla.texto == "Vence em 8 h"


def test_texto_da_duracao():
    assert sla.texto_duracao(45) == "45 min"
    assert sla.texto_duracao(3 * 60 + 20) == "3 h"
    assert sla.texto_duracao(2 * 1440 + 100) == "2 d"


def test_usuario_nao_recebe_etiqueta_nem_prazo(p):
    d = _abrir(p, "alta")
    visao = ordens.obter_os(p["sol"], d.id)
    texto = repr(dataclasses.asdict(visao)).lower()
    assert "prazo" not in texto and "sla" not in texto
    for item in ordens.listar_os(p["sol"]).itens:
        assert "prazo" not in repr(dataclasses.asdict(item)).lower()


def test_so_administrador_edita_alvos(p):
    for quem in ("man", "sol"):
        with pytest.raises(ErroPermissao):
            sla.definir_alvo(p[quem], p["f"], "alta", 60, 600)
        with pytest.raises(ErroPermissao):
            sla.listar_alvos(p[quem])
    with pytest.raises(ErroValidacao):
        sla.definir_alvo(p["admin"], p["f"], "alta", 0, 600)
    with pytest.raises(ErroValidacao):
        sla.definir_alvo(p["admin"], p["f"], "alta", 600, 60)


# --- Relatório -----------------------------------------------------------------------------


def test_cumprimento_puro():
    fim = T0 + 10 * H
    itens = [
        (T0 + H, T0 + 8 * H, T0 + H / 2, T0 + 7 * H),  # dentro, dentro
        (T0 + H, T0 + 8 * H, T0 + 2 * H, None),  # início fora; solução vencida: fora
        (T0 + 20 * H, T0 + 30 * H, None, None),  # ainda não venceu: fora do denominador
        (None, None, None, None),  # sem prazo
    ]
    inicio, solucao = sla.cumprimento(itens, fim)
    assert (inicio.dentro, inicio.total) == (1, 2)
    assert (solucao.dentro, solucao.total) == (1, 2)
    assert sla.texto_cumprimento(inicio) == "50% (1 de 2)"
    assert sla.texto_cumprimento(sla.Cumprimento(0, 0)) == "—"
    assert sla.texto_cumprimento(sla.Cumprimento(46, 50)) == "92% (46 de 50)"


def test_relatorio_do_mes(p):
    # 10/11: alta, iniciada em 2 h (dentro) e concluída em 10 h (dentro).
    a = _abrir(p, "alta", T0)
    a = _iniciar(p, a, T0 + 2 * H)
    _concluir(p, a, T0 + 10 * H)
    # 10/11: emergencial iniciada com 3 h (fora: prazo 1 h).
    b = _abrir(p, "emergencial", T0, titulo="Atrasada")
    _iniciar(p, b, T0 + 3 * H)
    # 30/11 22:00 Brasília (01/12 01:00 UTC): baixa, ainda no prazo no fim do mês: fora.
    _abrir(p, "baixa", datetime(2026, 12, 1, 1, 0, tzinfo=UTC), titulo="Fim do mês")
    p["r"].agora = datetime(2026, 12, 5, 12, 0, tzinfo=UTC)
    bloco = relatorios.relatorio_mensal(p["admin"], 2026, 11).mes_selecionado
    assert (bloco.sla_inicio.dentro, bloco.sla_inicio.total) == (1, 2)
    assert (bloco.sla_solucao.dentro, bloco.sla_solucao.total) == (1, 2)  # emergencial venceu
    por = {u: (i, s) for u, i, s in bloco.sla_por_urgencia}
    assert (por["alta"][0].dentro, por["alta"][0].total) == (1, 1)
    assert (por["emergencial"][0].dentro, por["emergencial"][0].total) == (0, 1)
    assert por["baixa"][0].total == 0 and sla.texto_cumprimento(por["baixa"][0]) == "—"
    assert relatorios.relatorio_mensal(p["admin"], 2026, 12).mes_selecionado.sla_inicio.total == 0


# --- Migração ------------------------------------------------------------------------------


def test_migracao_0018_com_dados(banco_vazio):
    cfg = config_alembic()
    command.upgrade(cfg, "0017")
    db.reiniciar()
    m = MetaData()
    m.reflect(bind=db.obter_engine())
    with db.obter_engine().begin() as c:
        c.execute(m.tables["filiais"].insert().values(id=1, codigo="1007", nome="A"))
        c.execute(
            m.tables["usuarios"]
            .insert()
            .values(
                id=1, nome="U", login="u", senha_hash="x", filial_id=1, papel="usuario", versao=1
            )
        )
        for os_id, origem, urgencia in ((1, "solicitacao", "alta"), (2, "manutencao", None)):
            c.execute(
                m.tables["ordens_servico"]
                .insert()
                .values(
                    id=os_id,
                    numero=f"1007-2026-00000{os_id}",
                    filial_id=1,
                    criado_por_id=1,
                    status="ABERTA",
                    titulo="T",
                    descricao="",
                    criado_em=T0,
                    atualizado_em=T0,
                    origem=origem,
                    urgencia=urgencia,
                    aberta_em=T0,
                    versao=1,
                )
            )
    command.upgrade(cfg, "0018")
    db.reiniciar()
    m2 = MetaData()
    m2.reflect(bind=db.obter_engine())
    os_ = m2.tables["ordens_servico"]
    with db.obter_engine().connect() as c:
        assert c.execute(select(m2.tables["sla_alvos"])).all().__len__() == 4
    # Na 0018 o modelo atual (com colunas posteriores) não serve: lê pela tabela refletida.
    with db.obter_engine().connect() as c:
        prazos = dict(
            (i, (pi, ps))
            for i, pi, ps in c.execute(
                select(os_.c.id, os_.c.prazo_inicio_em, os_.c.prazo_solucao_em)
            ).all()
        )
    from osapp.models.tipos import DataHoraUTC

    conv = DataHoraUTC().process_result_value
    assert conv(prazos[1][0], None) == T0 + 4 * H and conv(prazos[1][1], None) == T0 + 48 * H
    assert prazos[2] == (None, None)
    command.downgrade(cfg, "0017")
    m3 = MetaData()
    m3.reflect(bind=db.obter_engine())
    assert "sla_alvos" not in m3.tables and "prazo_inicio_em" not in m3.tables["ordens_servico"].c
    assert os_ is not None
    command.upgrade(cfg, "head")


def test_tela_em_dias_e_selo():
    from osapp.services import sla as s
    from osapp.ui.components import basicos
    from osapp.ui.views.sla import em_dias

    assert em_dias(60) == "" and em_dias(1440) == "= 1 dia"
    assert em_dias(2 * 1440) == "= 2 dias" and em_dias(1440 + 720) == "= 1 dia e 12 h"
    for codigo, texto in (
        ("atrasada", "Atrasada"),
        ("vence", "Vence em 3 h"),
        ("no_prazo", "No prazo"),
    ):
        selo = basicos.selo_sla(s.Etiqueta(codigo, texto))
        textos = [c.value for c in selo.content.controls if hasattr(c, "value")]
        assert texto in textos  # a cor nunca é o único sinal
    assert basicos.selo_sla(None) is None
