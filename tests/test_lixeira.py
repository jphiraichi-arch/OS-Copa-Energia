"""Prompt 24: exclusão lógica (lixeira) e prioridade sugerida pela urgência."""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import MetaData, select
from sqlalchemy.exc import IntegrityError

from osapp import db
from osapp.db import sessao
from osapp.models import OrdemServico
from osapp.models.ordem_servico import INCLUIR_EXCLUIDAS
from osapp.services import administracao, custos, lixeira, ordens, relatorios
from osapp.services.auth import carregar_ator
from osapp.services.erros import ErroNaoEncontrado, ErroPermissao, ErroValidacao
from tests.conftest import RAIZ, config_alembic
from tests.fabricas import categoria_id, especialidade_id, tipo_id
from tests.test_relatorio_tempos import BASE, DIA, SENHA, H, Relogio

M = timedelta(minutes=1)
MOTIVO = "Aberta em duplicidade por engano."


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
    }


def solicitacao(p, tempo, minuto, titulo, item, urgencia="alta", prioridade=None):
    tempo.agora = BASE + minuto * M
    v = ordens.criar_solicitacao(p["sol"], titulo, "Pedido do setor.", urgencia)
    d = ordens.obter_os(p["man"], v.id)
    campos = {
        "tempo_previsto_minutos": 60,
        "tipo_id": tipo_id(),
        "especialidade_id": especialidade_id(),
    }
    if prioridade:
        campos["prioridade"] = prioridade
    d = ordens.editar_os(p["man"], d.id, d.versao, campos)
    return custos.adicionar_item(
        p["man"], d.id, d.versao, "PREVISTO", categoria_id(), item, Decimal("1"), 1000
    )


def versao(os_id, ator):
    return ordens.obter_os(ator, os_id).versao


@pytest.fixture
def duas(p, tempo):
    """Visível e excluída, ambas na 1007 e com 'balança' num item."""
    visivel = solicitacao(p, tempo, 0, "Visível", "Balança comum")
    alvo = solicitacao(p, tempo, 1, "Alvo exclusivo", "Balança Exclusiva da Lixeira")
    tempo.agora = BASE + 2 * H
    return visivel, alvo


def excluir(p, alvo, motivo=MOTIVO):
    return lixeira.excluir_os(p["admin"], alvo.id, versao(alvo.id, p["admin"]), motivo)


def _ids(ator, termo=None, escopo=ordens.ESCOPO_ITENS):
    return {i.id for i in ordens.listar_os(ator, termo, None, None, 1, None, escopo).itens}


# --- Invisível para todos --------------------------------------------------------------


def test_excluida_some_de_tudo_para_todos(p, duas):
    visivel, alvo = duas
    excluir(p, alvo)
    filial = carregar_ator(p["man"]).filial_id
    for papel in ("sol", "man", "admin"):
        ator = p[papel]
        # Lista e busca (os dois escopos; o usuario busca no título e na descrição).
        assert alvo.id not in _ids(ator) and visivel.id in _ids(ator)
        for escopo in ordens.ESCOPOS:
            assert alvo.id not in _ids(ator, "balanca", escopo)
            assert alvo.id not in _ids(ator, "exclusivo", escopo)
            assert alvo.id not in _ids(ator, alvo.numero, escopo)  # pelo número
        # Detalhe: o mesmo 'não encontrada' de uma ordem inexistente.
        with pytest.raises(ErroNaoEncontrado):
            ordens.obter_os(ator, alvo.id)
        # Contadores (faixa e selo).
        c = ordens.contadores(ator)
        assert (c.abertas, c.aguardando_inicio) == (1, 1)
    for papel in ("man", "admin"):
        with pytest.raises(ErroNaoEncontrado):
            ordens.listar_eventos(p[papel], alvo.id)
        # Sugestões de descrição de item.
        sugestoes = custos.sugerir_descricoes(p[papel], filial, "balan")
        assert sugestoes == ["Balança comum"]
        # Relatório de tempos (com e sem busca) e relatório mensal.
        r = relatorios.relatorio_tempos(p[papel], DIA, DIA)
        assert r.total_no_periodo == 1 and r.backlog.quantidade == 1
        rb = relatorios.relatorio_tempos(p[papel], DIA, DIA, termo="balanca")
        assert (rb.busca.correspondentes, rb.busca.total_periodo) == (1, 1)
        mensal = relatorios.gerar_relatorio(p[papel], DIA.year, DIA.month)
        assert {c.status: c.total for c in mensal.basico.por_status}["ABERTA"] == 1
        assert mensal.basico.criadas_no_mes == 1


def test_restaurar_traz_de_volta_com_o_mesmo_numero(p, duas):
    visivel, alvo = duas
    excluir(p, alvo)
    pagina = lixeira.listar_excluidas(p["admin"])
    assert [i.numero for i in pagina.itens] == [alvo.numero]
    item = pagina.itens[0]
    assert (item.status, item.motivo, item.excluida_por_nome) == ("ABERTA", MOTIVO, "Ana")
    x = lixeira.obter_excluida(p["admin"], alvo.id)
    assert x.os.numero == alvo.numero and x.motivo == MOTIVO
    assert not any(vars(x.os.acoes).values())  # só leitura
    lixeira.restaurar_os(p["admin"], alvo.id, x.os.versao)
    for papel in ("sol", "man", "admin"):
        assert alvo.id in _ids(p[papel])
        assert ordens.obter_os(p[papel], alvo.id).numero == alvo.numero
        assert ordens.contadores(p[papel]).abertas == 2
    assert alvo.id in _ids(p["man"], "exclusiva")
    filial = carregar_ator(p["man"]).filial_id
    assert len(custos.sugerir_descricoes(p["man"], filial, "balan")) == 2
    assert relatorios.relatorio_tempos(p["man"], DIA, DIA).total_no_periodo == 2
    assert lixeira.listar_excluidas(p["admin"]).itens == ()


def test_busca_na_lixeira(p, duas):
    _visivel, alvo = duas
    excluir(p, alvo)
    assert len(lixeira.listar_excluidas(p["admin"], "exclusiva").itens) == 1
    assert lixeira.listar_excluidas(p["admin"], "inexistente").itens == ()


# --- Permissões e motivo -------------------------------------------------------------


def test_so_o_administrador_usa_a_lixeira(p, duas):
    _visivel, alvo = duas
    for papel in ("sol", "man"):
        with pytest.raises(ErroPermissao):
            lixeira.excluir_os(p[papel], alvo.id, versao(alvo.id, p["man"]), MOTIVO)
    excluir(p, alvo)
    for papel in ("sol", "man"):
        with pytest.raises(ErroPermissao):
            lixeira.restaurar_os(p[papel], alvo.id, 1)
        with pytest.raises(ErroPermissao):
            lixeira.listar_excluidas(p[papel])
        with pytest.raises(ErroPermissao):
            lixeira.obter_excluida(p[papel], alvo.id)


@pytest.mark.parametrize("motivo", [None, "", "          ", "x" * 9, "  123456789  ", "x" * 501])
def test_motivo_invalido_e_recusado(p, duas, motivo):
    _visivel, alvo = duas
    with pytest.raises(ErroValidacao):
        excluir(p, alvo, motivo)
    assert ordens.obter_os(p["admin"], alvo.id).id == alvo.id  # nada mudou


@pytest.mark.parametrize("motivo", ["x" * 10, "  " + "y" * 10 + "  ", "z" * 500])
def test_motivo_de_10_a_500_caracteres(p, duas, motivo):
    _visivel, alvo = duas
    excluir(p, alvo, motivo)
    assert lixeira.obter_excluida(p["admin"], alvo.id).motivo == motivo.strip()


def test_exclusao_em_qualquer_status(p, duas, tempo):
    visivel, _alvo = duas
    d = ordens.obter_os(p["man"], visivel.id)
    d = ordens.iniciar_execucao(p["man"], d.id, d.versao)
    lixeira.excluir_os(p["admin"], d.id, d.versao, MOTIVO)
    assert lixeira.obter_excluida(p["admin"], d.id).os.status == "EM_EXECUCAO"


# --- Nada muda enquanto excluída -----------------------------------------------------


def test_excluida_nao_pode_ser_mexida(p, duas, tempo):
    visivel, alvo = duas
    em_execucao = ordens.iniciar_execucao(p["man"], visivel.id, versao(visivel.id, p["man"]))
    excluir(p, alvo)
    lixeira.excluir_os(p["admin"], em_execucao.id, em_execucao.versao, MOTIVO)
    item = alvo.itens[0]
    tentativas = [
        lambda a: ordens.editar_os(a, alvo.id, alvo.versao, {"tempo_previsto_minutos": 30}),
        lambda a: ordens.iniciar_execucao(a, alvo.id, alvo.versao),
        lambda a: ordens.cancelar(a, alvo.id, alvo.versao),
        lambda a: ordens.desfazer_inicio(a, em_execucao.id, em_execucao.versao),
        lambda a: ordens.concluir_os(
            a,
            em_execucao.id,
            em_execucao.versao,
            [custos.ItemEntrada(categoria_id(), "Feito", Decimal("1"), 1)],
            tempo.agora - 2 * H,
            tempo.agora - H,
            "Feito.",
            "Pronto.",
        ),
        lambda a: custos.adicionar_item(
            a, alvo.id, alvo.versao, "PREVISTO", categoria_id(), "Outro", Decimal("1"), 1
        ),
        lambda a: custos.editar_item(a, alvo.id, item.id, alvo.versao, {"descricao": "Nova"}),
        lambda a: custos.remover_item(a, alvo.id, item.id, alvo.versao),
    ]
    for papel in ("man", "admin"):
        for tentativa in tentativas:
            with pytest.raises(ErroNaoEncontrado):
                tentativa(p[papel])
    with pytest.raises(ErroNaoEncontrado):
        ordens.editar_solicitacao(p["sol"], alvo.id, alvo.versao, {"titulo": "Outro título"})
    with pytest.raises(ErroNaoEncontrado):
        lixeira.excluir_os(p["admin"], alvo.id, alvo.versao, MOTIVO)  # já está na lixeira
    x = lixeira.obter_excluida(p["admin"], alvo.id)
    assert x.os.titulo == "Alvo exclusivo" and len(x.os.itens) == 1  # intacta


def test_eventos_de_exclusao_e_restauracao(p, duas):
    _visivel, alvo = duas
    excluir(p, alvo)
    x = lixeira.obter_excluida(p["admin"], alvo.id)
    ultimo = x.eventos[-1]
    assert (ultimo.tipo, ultimo.campo, ultimo.valor_antigo, ultimo.valor_novo) == (
        ordens.TIPO_EXCLUSAO,
        "exclusao",
        None,
        MOTIVO,
    )
    lixeira.restaurar_os(p["admin"], alvo.id, x.os.versao)
    eventos = ordens.listar_eventos(p["admin"], alvo.id)
    assert [e.tipo for e in eventos[-2:]] == [ordens.TIPO_EXCLUSAO, ordens.TIPO_RESTAURACAO]
    assert eventos[-1].valor_antigo == MOTIVO and eventos[-1].nome_usuario == "Ana"

    from osapp.ui import historico

    assert "Motivo: " + MOTIVO in historico.frase(eventos[-2])
    assert MOTIVO in historico.frase(eventos[-1]) and "restaurada" in historico.frase(eventos[-1])


def test_numero_nunca_e_reutilizado(p, duas, tempo):
    _visivel, alvo = duas
    excluir(p, alvo)  # a última ordem criada
    nova = solicitacao(p, tempo, 3, "Depois da exclusão", "Correia")
    prefixo, seq = alvo.numero.rsplit("-", 1)
    assert nova.numero == f"{prefixo}-{int(seq) + 1:06d}"


# --- Sem exclusão física -------------------------------------------------------------

DELETE_PROIBIDO = re.compile(
    r"delete\(\s*OrdemServico\b|DELETE\s+FROM\s+[\"']?ordens_servico|\.delete\(\s*(ordem|ordens?_)",
    re.IGNORECASE,
)


def test_nenhum_codigo_apaga_ordem_de_servico():
    achados = []
    for arquivo in (RAIZ / "src").rglob("*.py"):
        if "__pycache__" in arquivo.parts:
            continue
        for n, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
            if DELETE_PROIBIDO.search(linha):
                achados.append(f"{arquivo.relative_to(RAIZ)}:{n}")
    assert achados == []
    assert DELETE_PROIBIDO.search("s.delete(ordem)")
    assert DELETE_PROIBIDO.search("conexao.execute(delete(OrdemServico))")
    assert DELETE_PROIBIDO.search('text("DELETE FROM ordens_servico")')


def test_session_delete_de_uma_ordem_falha(p, duas):
    visivel, _alvo = duas
    with pytest.raises(RuntimeError, match="proibida"):
        with sessao() as s:
            s.delete(s.get(OrdemServico, visivel.id))
    assert ordens.obter_os(p["admin"], visivel.id).id == visivel.id


def test_check_exige_os_tres_campos_juntos(p, duas):
    visivel, _alvo = duas
    with pytest.raises(IntegrityError):
        with sessao() as s:
            ordem = s.get(OrdemServico, visivel.id)
            ordem.motivo_exclusao = "só o motivo, sem data"


def test_filtro_central_alcanca_get_contagem_e_subconsultas(p, duas):
    """Session.get, agregados, EXISTS dos itens e consultas a partir de os_itens_custo."""
    from sqlalchemy import func

    from osapp.models import OsItemCusto

    _visivel, alvo = duas
    excluir(p, alvo)
    with sessao() as s:
        assert s.get(OrdemServico, alvo.id) is None
        assert s.get(OrdemServico, alvo.id, execution_options={INCLUIR_EXCLUIDAS: True})
        assert s.scalar(select(func.count()).select_from(OrdemServico)) == 1
        por_item = select(func.count(OsItemCusto.id)).where(OsItemCusto.os_id == OrdemServico.id)
        assert s.scalar(por_item) == 1
        com_join = select(OsItemCusto.descricao).join(
            OrdemServico, OsItemCusto.os_id == OrdemServico.id
        )
        assert s.scalars(com_join).all() == ["Balança comum"]


# --- Prioridade sugerida pela urgência (parte B) ------------------------------------


def _eventos_prioridade(ator, os_id):
    return [e for e in ordens.listar_eventos(ator, os_id) if e.campo == "prioridade"]


def test_iniciar_sem_prioridade_copia_a_urgencia(p, tempo):
    d = solicitacao(p, tempo, 0, "Sem prioridade", "Peça", urgencia="emergencial")
    assert d.prioridade is None
    assert "Prioridade" not in " ".join(d.pendencias_para_iniciar)
    assert d.acoes.pode_iniciar  # previsto completo: a prioridade vem da urgência
    d = ordens.iniciar_execucao(p["man"], d.id, d.versao)
    assert (d.prioridade, d.urgencia, d.status) == ("emergencial", "emergencial", "EM_EXECUCAO")
    eventos = _eventos_prioridade(p["man"], d.id)
    assert len(eventos) == 1
    e = eventos[0]
    assert (e.tipo, e.valor_antigo, e.valor_novo) == (ordens.TIPO_EDICAO, None, "emergencial")
    assert e.observacao == ordens.NOTA_PRIORIDADE_DA_URGENCIA

    from osapp.ui import historico

    assert "Sugerida pela urgência do solicitante" in historico.frase(e)


def test_prioridade_escolhida_e_mantida(p, tempo):
    d = solicitacao(p, tempo, 0, "Com prioridade", "Peça", urgencia="baixa", prioridade="alta")
    d = ordens.iniciar_execucao(p["man"], d.id, d.versao)
    assert (d.prioridade, d.urgencia) == ("alta", "baixa")
    eventos = _eventos_prioridade(p["man"], d.id)
    assert len(eventos) == 1 and eventos[0].observacao is None  # só a escolha manual


def test_depois_a_prioridade_muda_como_edicao_comum_e_a_urgencia_nunca(p, tempo):
    d = solicitacao(p, tempo, 0, "Mudança posterior", "Peça", urgencia="media")
    d = ordens.iniciar_execucao(p["man"], d.id, d.versao)
    d = ordens.editar_os(p["man"], d.id, d.versao, {"prioridade": "alta"})
    assert (d.prioridade, d.urgencia) == ("alta", "media")
    eventos = _eventos_prioridade(p["man"], d.id)
    assert [(e.valor_antigo, e.valor_novo, e.observacao) for e in eventos] == [
        (None, "media", ordens.NOTA_PRIORIDADE_DA_URGENCIA),
        ("media", "alta", None),
    ]


def test_ordem_da_manutencao_ainda_exige_prioridade(p):
    d = ordens.criar_os(
        p["man"],
        "Ordem interna",
        "Sem urgência.",
        [custos.ItemEntrada(categoria_id(), "Peça", Decimal("1"), 1)],
        60,
        tipo_id=tipo_id(),
        especialidade_id=especialidade_id(),
    )
    assert d.pendencias_para_iniciar == (ordens.PENDENCIA_PRIORIDADE,)
    with pytest.raises(ErroValidacao):
        ordens.iniciar_execucao(p["man"], d.id, d.versao)


def test_relatorio_sem_dados_do_dia_seguinte(p, duas):
    """Sanidade: o dia do relatório é DIA (os testes acima dependem disso)."""
    assert DIA == date(2026, 5, 10)


# --- Migração 0011 com dados -----------------------------------------------------------


def test_migracao_0011_com_dados(banco_vazio):
    cfg = config_alembic()
    command.upgrade(cfg, "0010")
    db.reiniciar()
    m = MetaData()
    m.reflect(bind=db.obter_engine())
    t = m.tables
    from datetime import UTC, datetime

    t0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    with db.obter_engine().begin() as c:
        c.execute(t["filiais"].insert().values(id=1, codigo="1007", nome="Jardinópolis"))
        c.execute(
            t["usuarios"]
            .insert()
            .values(id=1, nome="Ana", login="ana", senha_hash="x", filial_id=1, papel="admin")
        )
        c.execute(
            t["ordens_servico"]
            .insert()
            .values(
                id=1,
                numero="1007-2026-000001",
                titulo="Antiga",
                descricao="x",
                filial_id=1,
                criado_por_id=1,
                status="ABERTA",
                criado_em=t0,
                atualizado_em=t0,
                aberta_em=t0,
                versao=1,
            )
        )
        c.execute(
            t["os_eventos"].insert().values(os_id=1, usuario_id=1, data_hora=t0, tipo="CRIACAO")
        )
    command.upgrade(cfg, "0011")
    db.reiniciar()
    # Na 0011 o modelo atual (com as colunas da 0012) ainda não serve: lê e grava pelas
    # tabelas refletidas, como a lixeira gravaria.
    m = MetaData()
    m.reflect(bind=db.obter_engine())
    os_, ev = m.tables["ordens_servico"], m.tables["os_eventos"]
    with db.obter_engine().begin() as c:
        assert c.execute(select(os_.c.excluida_em)).scalars().all() == [None]  # visível
        assert c.execute(select(ev.c.observacao)).scalars().all() == [None]
        c.execute(os_.update().values(excluida_em=t0, excluida_por_id=1, motivo_exclusao=MOTIVO))
        c.execute(
            ev.insert().values(
                os_id=1, usuario_id=1, data_hora=t0, tipo="EXCLUSAO", valor_novo=MOTIVO
            )
        )
    command.downgrade(cfg, "0010")
    db.reiniciar()
    m = MetaData()
    m.reflect(bind=db.obter_engine())
    assert "excluida_em" not in m.tables["ordens_servico"].c
    assert "observacao" not in m.tables["os_eventos"].c
    with db.obter_engine().connect() as c:
        assert c.execute(select(m.tables["ordens_servico"].c.numero)).scalars().all() == [
            "1007-2026-000001"
        ]
        tipos = c.execute(select(m.tables["os_eventos"].c.tipo)).scalars().all()
        assert tipos == ["CRIACAO", "EXCLUSAO"]
    command.upgrade(cfg, "head")
