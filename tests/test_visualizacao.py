"""Prompt 42: indicador 'Visualizada' (a manutenção abriu o detalhe)."""

from __future__ import annotations

import dataclasses
import os
import threading
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import MetaData, func, select

from osapp import db
from osapp.db import sessao
from osapp.models import OsEvento, OsVisualizacao
from osapp.services import (
    administracao,
    custos,
    ordens,
    relatorios,
    relogio,
    visualizacoes,
)
from tests.conftest import config_alembic
from tests.fabricas import categoria_id, especialidade_id, tipo_id

SENHA = "senha-ficticia-123"
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
    administracao.criar_filial("1007", "Jardinópolis")

    def criar(nome, login, papel):
        return administracao.criar_usuario(nome, login, SENHA, "1007", papel=papel).id

    return {
        "r": r,
        "admin": criar("Ana Admin", "ana.admin", "admin"),
        "man": criar("Mário Souza", "mario.man", "manutencao"),
        "man2": criar("Paula Lima", "paula.man", "manutencao"),
        "sol": criar("Sônia", "sonia.sol", "usuario"),
    }


def _linhas():
    with sessao() as s:
        return list(s.scalars(select(OsVisualizacao).order_by(OsVisualizacao.id)))


def _eventos_vis(os_id):
    with sessao() as s:
        return list(
            s.scalars(
                select(OsEvento).where(
                    OsEvento.os_id == os_id, OsEvento.tipo == visualizacoes.TIPO_VISUALIZACAO
                )
            )
        )


def _pedido(p, titulo="Bomba parada", urgencia="alta"):
    return ordens.criar_solicitacao(p["sol"], titulo, "Desc.", urgencia)


# --- Quem conta -----------------------------------------------------------------------------


def test_manutencao_abrindo_o_detalhe_marca(p):
    v = _pedido(p)
    assert visualizacoes.registrar_visualizacao(p["man"], v.id) is True
    assert [(x.os_id, x.usuario_id) for x in _linhas()] == [(v.id, p["man"])]
    d = ordens.obter_os(p["admin"], v.id)
    assert [x.nome for x in d.visualizacoes] == ["Mário Souza"]


def test_lista_busca_contadores_e_relatorio_nao_marcam(p):
    v = _pedido(p)
    ordens.listar_os(p["man"])
    ordens.listar_os(p["man"], "Bomba")
    ordens.contadores(p["man"])
    ordens.obter_os(p["man"], v.id)  # o serviço de leitura não registra; só a tela chama
    p["r"].agora = T0 + timedelta(days=30)
    relatorios.relatorio_mensal(p["admin"], 2026, 11)
    assert _linhas() == []


def test_usuario_admin_e_solicitante_nao_marcam(p):
    v = _pedido(p)
    assert visualizacoes.registrar_visualizacao(p["sol"], v.id) is False
    assert visualizacoes.registrar_visualizacao(p["admin"], v.id) is False
    propria = ordens.criar_solicitacao(p["man"], "Aberta pela manutenção", "Desc.", "baixa")
    assert visualizacoes.registrar_visualizacao(p["man"], propria.id) is False  # solicitante
    assert _linhas() == []


def test_os_da_manutencao_nao_tem_visualizacao_nem_indicador(p):
    d = ordens.criar_os(p["man2"], "OS interna", "Desc.", [])
    assert visualizacoes.registrar_visualizacao(p["man"], d.id) is False
    assert ordens.obter_os(p["man"], d.id).visualizacoes is None
    item = next(i for i in ordens.listar_os(p["man"]).itens if i.id == d.id)
    assert item.visualizada is None


# --- Histórico: só a primeira por pessoa ---------------------------------------------------


def test_so_a_primeira_vai_para_o_historico(p):
    v = _pedido(p)
    visualizacoes.registrar_visualizacao(p["man"], v.id)
    p["r"].agora = T0 + 2 * H
    assert visualizacoes.registrar_visualizacao(p["man"], v.id) is False
    linha = _linhas()[0]
    assert linha.primeira_visualizacao_em == T0 and linha.ultima_visualizacao_em == T0 + 2 * H
    assert [e.valor_novo for e in _eventos_vis(v.id)] == ["Mário Souza"]
    visualizacoes.registrar_visualizacao(p["man2"], v.id)
    assert [e.valor_novo for e in _eventos_vis(v.id)] == ["Mário Souza", "Paula Lima"]
    from osapp.ui import historico

    frases = [historico.frase(e) for e in ordens.listar_eventos(p["man"], v.id)]
    assert "Visualizada por Mário Souza" in frases


# --- Iniciar sem ter aberto ------------------------------------------------------------------


def test_iniciar_registra_a_visualizacao(p):
    v = _pedido(p)
    d = ordens.obter_os(p["man"], v.id)
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
        p["man"], d.id, d.versao, "PREVISTO", categoria_id(), "Peça", Decimal("1"), 100
    )
    p["r"].agora = T0 + H
    iniciada = ordens.iniciar_execucao(p["man"], d.id, d.versao)
    linha = _linhas()[0]
    assert linha.primeira_visualizacao_em <= iniciada.inicio_execucao_em
    assert len(_eventos_vis(v.id)) == 1


# --- O usuario recebe só o indicador ---------------------------------------------------------


def test_usuario_recebe_so_indicador_primeiro_e_quando(p):
    v = _pedido(p)
    antes = ordens.obter_os(p["sol"], v.id)
    assert (antes.visualizada, antes.primeiro_visualizador) == (False, None)
    visualizacoes.registrar_visualizacao(p["man"], v.id)
    p["r"].agora = T0 + H
    visualizacoes.registrar_visualizacao(p["man2"], v.id)
    visao = ordens.obter_os(p["sol"], v.id)
    assert (visao.visualizada, visao.primeiro_visualizador, visao.primeira_visualizacao_em) == (
        True,
        "Mário Souza",
        T0,
    )
    texto = repr(dataclasses.asdict(visao))
    assert "Paula" not in texto and "ultima" not in texto
    assert "custo" not in texto and "previsto" not in texto.replace("pode_", "")
    item = ordens.listar_os(p["sol"]).itens[0]
    assert item.visualizada is True
    assert set(dataclasses.asdict(item)) & {"visualizacoes", "primeiro_visualizador"} == set()
    from osapp.ui.views.detalhe import texto_visualizacao_solicitante

    assert texto_visualizacao_solicitante(visao).startswith("Visualizada por Mário Souza em ")
    assert texto_visualizacao_solicitante(antes) == "Ainda não visualizada pela manutenção"


def test_falha_ao_registrar_nao_impede_abrir(p, monkeypatch, caplog):
    v = _pedido(p)

    def quebra(*_a, **_k):
        raise RuntimeError("banco instável")

    monkeypatch.setattr(visualizacoes, "_upsert", quebra)
    assert visualizacoes.registrar_visualizacao(p["man"], v.id) is False
    assert "Falha ao registrar a visualização" in caplog.text
    assert ordens.obter_os(p["man"], v.id).id == v.id


def test_filtro_nao_visualizadas(p):
    a = _pedido(p, "Primeira")
    b = _pedido(p, "Segunda")
    visualizacoes.registrar_visualizacao(p["man"], a.id)
    ids = {i.id for i in ordens.listar_os(p["man"], nao_visualizadas=True).itens}
    assert ids == {b.id}


# --- Concorrência (PostgreSQL) ---------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("OS_TEST_DATABASE_URL"), reason="concorrência real só no PostgreSQL"
)
def test_primeiras_visualizacoes_simultaneas_criam_uma_linha(p):
    v = _pedido(p)
    barreira = threading.Barrier(8)
    resultados = []

    def abrir():
        barreira.wait()
        resultados.append(visualizacoes.registrar_visualizacao(p["man"], v.id))

    threads = [threading.Thread(target=abrir) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with sessao() as s:
        assert s.scalar(select(func.count()).select_from(OsVisualizacao)) == 1
    assert resultados.count(True) == 1 and len(_eventos_vis(v.id)) == 1


# --- Relatório ------------------------------------------------------------------------------------


def test_relatorio_tempo_ate_visualizacao_e_etapas(p):
    # A: aberta T0, vista T0+1h (Mário), iniciada T0+3h.
    a = _pedido(p, "Pedido A", "alta")
    p["r"].agora = T0 + H
    visualizacoes.registrar_visualizacao(p["man"], a.id)
    d = ordens.obter_os(p["man"], a.id)
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
        p["man"], d.id, d.versao, "PREVISTO", categoria_id(), "Peça", Decimal("1"), 100
    )
    p["r"].agora = T0 + 3 * H
    ordens.iniciar_execucao(p["man"], d.id, d.versao)
    # B: aberta T0, vista só em dezembro (depois do fim do período de novembro).
    p["r"].agora = T0
    b = _pedido(p, "Pedido B", "baixa")
    p["r"].agora = datetime(2026, 12, 2, 12, 0, tzinfo=UTC)
    visualizacoes.registrar_visualizacao(p["man"], b.id)
    bloco = relatorios.relatorio_mensal(p["admin"], 2026, 11).mes_selecionado
    assert (bloco.tempo_ate_visualizacao.n, bloco.tempo_ate_visualizacao.media_segundos) == (
        1,
        3600,
    )
    assert (bloco.visualizada_ate_inicio.n, bloco.visualizada_ate_inicio.media_segundos) == (
        1,
        2 * 3600,
    )
    por = dict(bloco.visualizacao_por_urgencia)
    assert por["alta"].n == 1 and por["baixa"].n == 0
    assert bloco.nao_visualizadas == 1  # B: vista só depois do fim de novembro
    fim_nov = datetime(2026, 12, 1, 3, 0, tzinfo=UTC)  # 01/12 00:00 em Brasília
    assert bloco.nao_visualizada_mais_antiga_segundos == int((fim_nov - T0).total_seconds())
    dez = relatorios.relatorio_mensal(p["admin"], 2026, 12).acumulado
    assert dez.tempo_ate_visualizacao.n == 2 and dez.nao_visualizadas == 0


def test_texto_nao_visualizadas():
    from osapp.ui.views.relatorio_tempos import texto_nao_visualizadas

    assert texto_nao_visualizadas(0, None) == "Nenhuma"
    assert texto_nao_visualizadas(3, 2 * 86400).startswith("3 (a mais antiga há ")


def test_indicador_tem_texto_e_icone():
    from osapp.ui import theme
    from osapp.ui.components import basicos

    assert basicos.selo_visualizacao(None) is None
    for valor, texto in ((True, "Visualizada"), (False, "Não visualizada")):
        selo = basicos.selo_visualizacao(valor)
        textos = [c.value for c in selo.content.controls if hasattr(c, "value")]
        assert texto in textos
    fundo, cor = theme.COR_STATUS_OUTRO
    assert theme.contraste(cor, fundo) >= 4.5


# --- Migração ----------------------------------------------------------------------------------


def test_migracao_0020_com_dados(banco_vazio):
    cfg = config_alembic()
    command.upgrade(cfg, "head")
    db.reiniciar()
    administracao.criar_filial("1007", "A")
    uid = administracao.criar_usuario("U", "u.man", SENHA, "1007", papel="manutencao").id
    sid = administracao.criar_usuario("S", "s.sol", SENHA, "1007", papel="usuario").id
    v = ordens.criar_solicitacao(sid, "Pedido", "Desc.", "alta")
    visualizacoes.registrar_visualizacao(uid, v.id)
    command.downgrade(cfg, "0019")
    m = MetaData()
    m.reflect(bind=db.obter_engine())
    assert "os_visualizacoes" not in m.tables
    with db.obter_engine().connect() as c:
        assert c.execute(select(m.tables["ordens_servico"].c.titulo)).scalars().all() == ["Pedido"]
    command.upgrade(cfg, "head")
    db.reiniciar()
    assert _linhas() == []
