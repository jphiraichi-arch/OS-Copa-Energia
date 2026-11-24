"""Prompt 37: especialidade nas ordens e nos usuários; quebra no relatório."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import MetaData, select

from osapp import db
from osapp.services import administracao, custos, especialidades, ordens, relatorios, relogio
from osapp.services import usuarios as usuarios_srv
from osapp.services.erros import ErroPermissao, ErroValidacao
from osapp.ui import rotulos_eventos
from tests.conftest import config_alembic
from tests.fabricas import categoria_id, especialidade_id, tipo_id

SENHA = "senha-ficticia-123"
T0 = datetime(2026, 11, 10, 13, 0, tzinfo=UTC)


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
        "man": criar("Mário", "mario.man", "manutencao"),
        "sol": criar("Sônia", "sonia.sol", "usuario"),
    }


def _pronta(p, urgencia="alta", especialidade="MECANICA", titulo="Bomba"):
    v = ordens.criar_solicitacao(p["sol"], titulo, "Descrição.", urgencia)
    d = ordens.obter_os(p["man"], v.id)
    campos = {"tempo_previsto_minutos": 60, "tipo_id": tipo_id(), "prioridade": "media"}
    if especialidade:
        campos["especialidade_id"] = especialidade_id(especialidade)
    d = ordens.editar_os(p["man"], d.id, d.versao, campos)
    return custos.adicionar_item(
        p["man"], d.id, d.versao, "PREVISTO", categoria_id(), "Peça", Decimal("1"), 1000
    )


# --- Iniciar exige especialidade ------------------------------------------------------------


def test_iniciar_sem_especialidade_e_recusado_e_com_ela_inicia(p):
    d = _pronta(p, especialidade=None)
    assert ordens.PENDENCIA_ESPECIALIDADE in d.pendencias_para_iniciar
    with pytest.raises(ErroValidacao) as erro:
        ordens.iniciar_execucao(p["man"], d.id, d.versao)
    assert "especialidade" in erro.value.mensagem
    d = ordens.editar_os(
        p["man"], d.id, d.versao, {"especialidade_id": especialidade_id("ELETRICA")}
    )
    assert d.especialidade_nome == "Elétrica"
    assert ordens.iniciar_execucao(p["man"], d.id, d.versao).status == "EM_EXECUCAO"


def test_mudanca_vira_evento_com_rotulo(p):
    d = _pronta(p)
    ordens.editar_os(p["man"], d.id, d.versao, {"especialidade_id": especialidade_id("PREDIAL")})
    eventos = ordens.listar_eventos(p["man"], d.id)
    mudanca = [e for e in eventos if e.campo == "especialidade_id"]
    assert [(e.valor_antigo, e.valor_novo) for e in mudanca] == [
        (None, "Mecânica"),
        ("Mecânica", "Predial/civil"),
    ]
    assert rotulos_eventos.rotulo("especialidade_id") == "Especialidade"


# --- O usuario nunca define nem recebe ----------------------------------------------------


def test_usuario_nao_define_nem_recebe(p):
    d = _pronta(p)
    with pytest.raises(ErroPermissao):
        ordens.editar_os(p["sol"], d.id, d.versao, {"especialidade_id": especialidade_id()})
    with pytest.raises(ErroPermissao):
        ordens.editar_solicitacao(
            p["sol"], d.id, d.versao, {"especialidade_id": especialidade_id()}
        )
    visao = ordens.obter_os(p["sol"], d.id)
    texto = repr(dataclasses.asdict(visao))
    assert "especialidade" not in texto and "Mecânica" not in texto
    for item in ordens.listar_os(p["sol"]).itens:
        assert "especialidade" not in repr(dataclasses.asdict(item))
    with pytest.raises(ErroValidacao):
        ordens.listar_os(p["sol"], especialidade_id=especialidade_id())
    with pytest.raises(ErroPermissao):
        especialidades.listar(p["sol"])


# --- Desativada -------------------------------------------------------------------------------


def test_desativada_nao_entra_em_nova_mas_fica_na_antiga(p):
    antiga = _pronta(p, especialidade="UTILIDADES")
    esp = especialidade_id("UTILIDADES")
    especialidades.alterar(p["admin"], esp, ativo=False)
    assert esp not in {e.id for e in especialidades.listar(p["man"])}
    with pytest.raises(ErroValidacao) as erro:
        _pronta(p, especialidade="UTILIDADES", titulo="Outra")
    assert erro.value.campo == "especialidade_id"
    with pytest.raises(ErroValidacao):
        ordens.criar_os(p["man"], "OS nova", "Descrição.", [], especialidade_id=esp)
    d = ordens.obter_os(p["man"], antiga.id)
    assert d.especialidade_nome == "Utilidades"
    # A antiga continua editável e mantém a sua (mesmo valor reenviado é aceito).
    d = ordens.editar_os(
        p["man"], d.id, d.versao, {"especialidade_id": esp, "tempo_previsto_minutos": 90}
    )
    assert d.especialidade_id == esp and d.tempo_previsto_minutos == 90
    assert ordens.iniciar_execucao(p["man"], d.id, d.versao).status == "EM_EXECUCAO"


# --- Lista (administrador) ------------------------------------------------------------------


def test_administrador_gerencia_a_lista(p):
    nomes = [e.nome for e in especialidades.listar(p["man"])]
    assert nomes == ["Mecânica", "Elétrica", "Predial/civil", "Utilidades"]
    nova = especialidades.criar(p["admin"], "Refrigeração")
    assert nova.codigo == "REFRIGERACAO" and nova.ordem == 5
    with pytest.raises(ErroValidacao):
        especialidades.criar(p["admin"], "refrigeração")
    especialidades.alterar(p["admin"], nova.id, nome="Refrigeração e ar")
    lista = especialidades.mover(p["admin"], nova.id, -1)
    assert [e.nome for e in lista][-2:] == ["Refrigeração e ar", "Utilidades"]
    for chamada in (
        lambda a: especialidades.criar(a, "X y"),
        lambda a: especialidades.alterar(a, nova.id, nome="Z z"),
        lambda a: especialidades.mover(a, nova.id, 1),
        lambda a: especialidades.listar(a, True),
    ):
        with pytest.raises(ErroPermissao):
            chamada(p["man"])


def test_filtro_da_lista_por_especialidade(p):
    a = _pronta(p, especialidade="MECANICA", titulo="Mecânica 1")
    b = _pronta(p, especialidade="ELETRICA", titulo="Elétrica 1")
    vistos = {
        o.id
        for o in ordens.listar_os(p["man"], especialidade_id=especialidade_id("ELETRICA")).itens
    }
    assert vistos == {b.id} and a.id not in vistos


# --- Usuários ---------------------------------------------------------------------------------


def test_especialidades_do_usuario_so_para_manutencao(p):
    d = usuarios_srv.obter_usuario(p["admin"], p["man"])
    ids = [especialidade_id("MECANICA"), especialidade_id("ELETRICA")]
    d = usuarios_srv.alterar_usuario(p["admin"], d.id, d.versao, {"especialidades": ids})
    assert d.especialidades_nomes == ("Mecânica", "Elétrica")
    s = usuarios_srv.obter_usuario(p["admin"], p["sol"])
    with pytest.raises(ErroValidacao) as erro:
        usuarios_srv.alterar_usuario(p["admin"], s.id, s.versao, {"especialidades": ids})
    assert erro.value.mensagem == usuarios_srv.MSG_ESPECIALIDADES
    # Mudar o papel para usuario apaga as especialidades (com evento).
    d = usuarios_srv.alterar_usuario(p["admin"], d.id, d.versao, {"papel": "usuario"})
    assert d.especialidades == ()
    campos = [e.campo for e in usuarios_srv.listar_eventos_usuario(p["admin"], p["man"])]
    assert campos.count("especialidades") == 2


# --- Relatório ----------------------------------------------------------------------------------


def test_quebra_por_especialidade_pura():
    t = T0
    linhas = [
        (1, "alta", t, t + timedelta(hours=1), t + timedelta(hours=3), "CONCLUIDA", "", ""),
        (2, "alta", t, t + timedelta(hours=3), None, "EM_EXECUCAO", "", ""),
        (3, "baixa", t, None, None, "ABERTA", "", ""),
        (4, "baixa", t, t + timedelta(hours=2), None, "EM_EXECUCAO", "", ""),
    ]
    especialidade_de = {1: 10, 2: 10, 3: None, 4: None}
    nomes = [(10, "Mecânica"), (11, "Elétrica")]
    por = relatorios.medidas_por_especialidade(linhas, especialidade_de, nomes)
    assert [x.especialidade for x in por] == ["Mecânica", "Elétrica", "Não informada"]
    mec, ele, nao = por
    assert (mec.resposta.n, mec.resposta.media_segundos) == (2, 2 * 3600)
    assert (mec.solucao.n, mec.solucao.media_segundos) == (1, 3 * 3600)
    assert ele.resposta.n == 0 and ele.resposta.media_segundos is None
    assert (nao.resposta.n, nao.resposta.media_segundos) == (1, 2 * 3600)


def test_relatorio_mensal_traz_a_quebra_com_nao_informada(p):
    a = _pronta(p, especialidade="MECANICA", titulo="Com especialidade")
    p["r"].agora = T0 + timedelta(hours=2)
    ordens.iniciar_execucao(p["man"], a.id, ordens.obter_os(p["man"], a.id).versao)
    p["r"].agora = T0
    _pronta(p, especialidade=None, titulo="Antiga sem especialidade")
    p["r"].agora = T0 + timedelta(days=30)
    rel = relatorios.relatorio_mensal(p["admin"], 2026, 11)
    por = {x.especialidade: x for x in rel.mes_selecionado.por_especialidade}
    assert set(por) == {"Mecânica", "Elétrica", "Predial/civil", "Utilidades", "Não informada"}
    assert por["Mecânica"].resposta.n == 1
    assert por["Mecânica"].resposta.media_segundos == 2 * 3600
    assert por["Não informada"].resposta.n == 0
    assert rel.acumulado.por_especialidade[0].especialidade == "Mecânica"


# --- Migração ---------------------------------------------------------------------------------


def test_migracao_0017_com_dados(banco_vazio):
    cfg = config_alembic()
    command.upgrade(cfg, "0016")
    db.reiniciar()
    m = MetaData()
    m.reflect(bind=db.obter_engine())
    agora = datetime(2026, 1, 1, tzinfo=UTC)
    with db.obter_engine().begin() as c:
        c.execute(m.tables["filiais"].insert().values(id=1, codigo="1007", nome="A"))
        c.execute(
            m.tables["usuarios"]
            .insert()
            .values(
                id=1, nome="U", login="u", senha_hash="x", filial_id=1, papel="manutencao", versao=1
            )
        )
        c.execute(
            m.tables["ordens_servico"]
            .insert()
            .values(
                id=1,
                numero="1007-2026-000001",
                filial_id=1,
                criado_por_id=1,
                status="ABERTA",
                titulo="Antiga",
                descricao="",
                criado_em=agora,
                atualizado_em=agora,
                origem="solicitacao",
                urgencia="alta",
                aberta_em=agora,
                versao=1,
            )
        )
    command.upgrade(cfg, "0017")
    m2 = MetaData()
    m2.reflect(bind=db.obter_engine())
    with db.obter_engine().connect() as c:
        codigos = (
            c.execute(
                select(m2.tables["especialidades"].c.codigo).order_by(
                    m2.tables["especialidades"].c.ordem
                )
            )
            .scalars()
            .all()
        )
        assert codigos == ["MECANICA", "ELETRICA", "PREDIAL", "UTILIDADES"]
        assert c.execute(
            select(m2.tables["ordens_servico"].c.especialidade_id)
        ).scalars().all() == [None]
    command.downgrade(cfg, "0016")
    m3 = MetaData()
    m3.reflect(bind=db.obter_engine())
    assert "especialidades" not in m3.tables and "usuario_especialidades" not in m3.tables
    assert "especialidade_id" not in m3.tables["ordens_servico"].c
    with db.obter_engine().connect() as c:
        assert c.execute(select(m3.tables["ordens_servico"].c.titulo)).scalars().all() == ["Antiga"]
    command.upgrade(cfg, "head")
