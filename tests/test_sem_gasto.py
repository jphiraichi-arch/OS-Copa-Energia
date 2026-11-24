"""Prompt 31: 'Sem gasto' por fase no lugar de 'pelo menos um item de custo'."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import MetaData, select

from osapp import cli, db
from osapp.db import sessao
from osapp.models import Usuario
from osapp.services import custos, ordens, relatorios, relogio
from osapp.services.erros import (
    ErroAutenticacao,
    ErroNaoEncontrado,
    ErroPermissao,
    ErroValidacao,
)
from osapp.ui import historico
from tests.conftest import config_alembic
from tests.fabricas import categoria_id, especialidade_id, novo_usuario, tipo_id

T0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
MSG = "Adicione um item ou marque Sem gasto."


@pytest.fixture
def c(cenario, monkeypatch):
    monkeypatch.setattr(relogio, "agora", lambda: T0)
    with sessao() as s:
        filial = s.get(Usuario, cenario["marina"]).filial
        cenario["sol"] = novo_usuario(s, filial, "sol.um", "Sol Um", papel="usuario").id
    return cenario


def _item(valor=1000, descricao="Peça"):
    return custos.ItemEntrada(categoria_id(), descricao, Decimal("1"), valor)


def _sem_itens(c):
    """Solicitação com tempo, tipo e prioridade, sem nenhum item previsto."""
    v = ordens.criar_solicitacao(c["sol"], "Pedido sem custo", "Ajuste simples.", "media")
    d = ordens.obter_os(c["marina"], v.id)
    return ordens.editar_os(
        c["marina"],
        d.id,
        d.versao,
        {
            "tempo_previsto_minutos": 30,
            "tipo_id": tipo_id(),
            "especialidade_id": especialidade_id(),
            "prioridade": "media",
        },
    )


def _com_item(c, n=1):
    d = _sem_itens(c)
    for k in range(n):
        d = custos.adicionar_item(
            c["marina"], d.id, d.versao, "PREVISTO", categoria_id(), f"Peça {k}", Decimal("1"), 100
        )
    return d


def _concluir(c, d, itens=None, sem_gasto=False, ator="pedro", inicio=True):
    i = T0 - timedelta(hours=2) if inicio else None
    return ordens.concluir_os(
        c[ator],
        d.id,
        d.versao,
        itens or [],
        i,
        T0 - timedelta(hours=1),
        "Feito.",
        "Pronto, obrigado.",
        sem_gasto,
    )


def _eventos(c, os_id):
    return [
        (e.tipo, e.campo, e.valor_antigo, e.valor_novo)
        for e in ordens.listar_eventos(c["admin"], os_id)
    ]


# --- Iniciar e concluir --------------------------------------------------------------


def test_nao_inicia_sem_item_nem_sem_gasto(c):
    d = _sem_itens(c)
    assert ordens.PENDENCIA_VALOR in d.pendencias_para_iniciar and not d.acoes.pode_iniciar
    with pytest.raises(ErroValidacao) as erro:
        ordens.iniciar_execucao(c["marina"], d.id, d.versao)
    assert erro.value.mensagem == MSG and erro.value.campo == "itens_previstos"


def test_inicia_com_sem_gasto_ou_com_item(c):
    d = _sem_itens(c)
    d = ordens.definir_sem_gasto(c["marina"], d.id, d.versao, "PREVISTO", True)
    assert d.sem_gasto_previsto and d.pendencias_para_iniciar == () and d.acoes.pode_iniciar
    assert ordens.iniciar_execucao(c["marina"], d.id, d.versao).status == "EM_EXECUCAO"
    d2 = _com_item(c)
    assert ordens.iniciar_execucao(c["marina"], d2.id, d2.versao).status == "EM_EXECUCAO"


def test_conclusao_exige_item_ou_sem_gasto(c):
    d = ordens.iniciar_execucao(c["pedro"], *(lambda x: (x.id, x.versao))(_com_item(c)))
    with pytest.raises(ErroValidacao) as erro:
        _concluir(c, d)
    assert erro.value.mensagem == MSG and erro.value.campo == "itens_realizados"
    with pytest.raises(ErroValidacao):  # os dois ao mesmo tempo: nunca
        _concluir(c, d, itens=[_item()], sem_gasto=True)
    feita = _concluir(c, d, sem_gasto=True)
    assert feita.status == "CONCLUIDA" and feita.sem_gasto_realizado
    assert not [i for i in feita.itens if i.fase == "REALIZADO"]
    assert (ordens.TIPO_EDICAO, "sem_gasto_realizado", "false", "true") in _eventos(c, d.id)
    outra = _com_item(c)
    outra = ordens.iniciar_execucao(c["pedro"], outra.id, outra.versao)
    assert _concluir(c, outra, itens=[_item()]).status == "CONCLUIDA"


def test_tempos_continuam_obrigatorios_com_sem_gasto(c):
    v = ordens.criar_solicitacao(c["sol"], "Pedido sem tempo", "Sem custo.", "media")
    d = ordens.obter_os(c["marina"], v.id)
    d = ordens.editar_os(
        c["marina"], d.id, d.versao, {"tipo_id": tipo_id(), "especialidade_id": especialidade_id()}
    )
    d = ordens.definir_sem_gasto(c["marina"], d.id, d.versao, "PREVISTO", True)
    with pytest.raises(ErroValidacao):  # falta o tempo previsto
        ordens.iniciar_execucao(c["marina"], d.id, d.versao)
    d = ordens.editar_os(c["marina"], d.id, d.versao, {"tempo_previsto_minutos": 30})
    d = ordens.iniciar_execucao(c["pedro"], d.id, d.versao)
    with pytest.raises(ErroValidacao):  # falta o início realizado
        _concluir(c, d, sem_gasto=True, inicio=False)


# --- Marca e itens nunca juntos ------------------------------------------------------


def test_marcar_com_itens_e_recusado(c):
    d = _com_item(c)
    with pytest.raises(ErroValidacao):
        ordens.definir_sem_gasto(c["marina"], d.id, d.versao, "PREVISTO", True)


def test_incluir_item_desmarca_e_grava_evento(c):
    d = _sem_itens(c)
    d = ordens.definir_sem_gasto(c["marina"], d.id, d.versao, "PREVISTO", True)
    d = custos.adicionar_item(
        c["marina"], d.id, d.versao, "PREVISTO", categoria_id(), "Peça", Decimal("1"), 100
    )
    assert not d.sem_gasto_previsto and len(d.itens) == 1
    eventos = _eventos(c, d.id)
    assert (ordens.TIPO_EDICAO, "sem_gasto_previsto", "false", "true") in eventos
    assert eventos[-2:][0] == (ordens.TIPO_EDICAO, "sem_gasto_previsto", "true", "false")
    assert eventos[-1][0] == custos.TIPO_ITEM_ADICIONADO


def test_ultimo_item_em_execucao_e_trocar_para_sem_gasto(c):
    d = _com_item(c, n=2)
    d = ordens.iniciar_execucao(c["marina"], d.id, d.versao)
    primeiro, segundo = d.itens
    d = custos.remover_item(c["marina"], d.id, primeiro.id, d.versao)
    with pytest.raises(ErroValidacao):  # o último fica
        custos.remover_item(c["marina"], d.id, segundo.id, d.versao)
    antes = len(_eventos(c, d.id))
    d2 = ordens.trocar_para_sem_gasto(c["marina"], d.id, d.versao, "PREVISTO")
    assert d2.versao == d.versao + 1  # uma só transação
    assert d2.sem_gasto_previsto and d2.itens == ()
    novos = _eventos(c, d.id)[antes:]
    assert [e[0] for e in novos] == [custos.TIPO_ITEM_REMOVIDO, ordens.TIPO_EDICAO]
    assert novos[-1] == (ordens.TIPO_EDICAO, "sem_gasto_previsto", "false", "true")
    with pytest.raises(ErroValidacao) as erro:  # desmarcar e ficar sem nada: não
        ordens.definir_sem_gasto(c["marina"], d2.id, d2.versao, "PREVISTO", False)
    assert erro.value.mensagem == MSG


def test_trocar_com_tres_itens_grava_um_evento_por_item(c):
    d = _com_item(c, n=3)
    antes = len(_eventos(c, d.id))
    d = ordens.trocar_para_sem_gasto(c["marina"], d.id, d.versao, "PREVISTO")
    tipos = [e[0] for e in _eventos(c, d.id)[antes:]]
    assert tipos.count(custos.TIPO_ITEM_REMOVIDO) == 3 and tipos[-1] == ordens.TIPO_EDICAO


# --- Permissões e o usuario ------------------------------------------------------------


@pytest.mark.parametrize(
    ("ator", "esperado"),
    [
        ("marina", "ok"),  # manutenção da filial
        ("admin", "ok"),
        ("sol", ErroPermissao),  # usuario
        ("carlos", ErroNaoEncontrado),  # manutenção de outra filial
        ("inativa", ErroAutenticacao),
    ],
)
def test_permissoes_da_marca_prevista(c, ator, esperado):
    d = _sem_itens(c)
    if esperado == "ok":
        d = ordens.definir_sem_gasto(c[ator], d.id, d.versao, "PREVISTO", True)
        assert d.sem_gasto_previsto
    else:
        with pytest.raises(esperado):
            ordens.definir_sem_gasto(c[ator], d.id, d.versao, "PREVISTO", True)


def test_marca_realizada_so_admin_e_so_depois_da_conclusao(c):
    d = ordens.iniciar_execucao(c["pedro"], *(lambda x: (x.id, x.versao))(_com_item(c)))
    for ator in ("pedro", "admin"):  # antes da conclusão: só com a conclusão
        with pytest.raises(ErroPermissao):
            ordens.definir_sem_gasto(c[ator], d.id, d.versao, "REALIZADO", True)
    d = _concluir(c, d, itens=[_item()])
    with pytest.raises(ErroPermissao):
        ordens.trocar_para_sem_gasto(c["pedro"], d.id, d.versao, "REALIZADO")
    d = ordens.trocar_para_sem_gasto(c["admin"], d.id, d.versao, "REALIZADO")
    assert d.sem_gasto_realizado and not [i for i in d.itens if i.fase == "REALIZADO"]


def test_usuario_nunca_recebe_as_marcas(c):
    d = ordens.definir_sem_gasto(
        c["marina"], *(lambda x: (x.id, x.versao))(_sem_itens(c)), "PREVISTO", True
    )
    for modelo in (ordens.OsVisaoSolicitante, ordens.ResumoSolicitante):
        assert not [f for f in modelo.__dataclass_fields__ if "gasto" in f]
    v = ordens.obter_os(c["sol"], d.id)
    assert not hasattr(v, "sem_gasto_previsto")
    with pytest.raises(ErroPermissao):
        ordens.listar_eventos(c["sol"], d.id)


# --- Textos de diferença sem divisão por zero ----------------------------------------


def test_diferencas_com_zero():
    n, m = " ", "−"
    assert historico.texto_diferenca_valor(0, None) == f"R${n}0,00 — sem gasto"
    assert historico.texto_diferenca_valor(15000, None) == f"+R${n}150,00 (não previsto)"
    pct = custos.percentual(-10000, 10000)
    assert historico.texto_diferenca_valor(-10000, pct) == (
        f"R${n}100,00 abaixo do previsto ({m}100%)"
    )


def test_nenhuma_funcao_divide_por_zero():
    assert custos.percentual(0, 0) is None and custos.percentual(500, 0) is None
    vazio = custos.calcular_resumo([])
    assert vazio.diferenca_percentual is None and vazio.total_previsto_centavos == 0
    assert relatorios.taxa_de_conclusao(0, 0, 0).percentual is None
    assert relatorios.medir([]).media_segundos is None
    for dif in (0, 1, -1):
        for pct in (None, 0.0):
            historico.texto_diferenca_valor(dif, pct)
            historico.texto_diferenca_compacta(dif, pct)
    historico.texto_diferenca_tempo(0)
    from dataclasses import dataclass

    from osapp.ui import tabela_custos

    @dataclass
    class Linha:
        fase: str
        categoria_id: int = 1
        categoria_nome: str = "Peças"
        categoria_ordem: int = 1
        quantidade: Decimal = Decimal(1)
        valor_unitario_centavos: int = 0

    so_realizado = custos.calcular_resumo([Linha("REALIZADO", valor_unitario_centavos=15000)])
    linhas = tabela_custos.linhas(so_realizado, True)
    assert linhas[0].diferenca == "+R$ 150,00 (não previsto)"
    assert linhas[-1].diferenca == "+R$ 150,00 (não previsto)"
    zerado = custos.calcular_resumo([Linha("PREVISTO"), Linha("REALIZADO")])
    assert tabela_custos.linhas(zerado, True)[-1].diferenca == "R$ 0,00 — sem gasto"


# --- Relatório mensal --------------------------------------------------------------


def test_relatorio_conta_sem_gasto_como_zero(c, monkeypatch):
    monkeypatch.setenv("OS_TZ", "UTC")
    # A: previsto e realizado Sem gasto, concluída. B: 1000 previsto, 1500 realizado,
    # concluída. C: previsto Sem gasto, em execução.
    a = ordens.definir_sem_gasto(
        c["marina"], *(lambda x: (x.id, x.versao))(_sem_itens(c)), "PREVISTO", True
    )
    a = ordens.iniciar_execucao(c["pedro"], a.id, a.versao)
    _concluir(c, a, sem_gasto=True)
    b = _sem_itens(c)
    b = custos.adicionar_item(
        c["marina"], b.id, b.versao, "PREVISTO", categoria_id(), "Peça", Decimal("1"), 1000
    )
    b = ordens.iniciar_execucao(c["pedro"], b.id, b.versao)
    _concluir(c, b, itens=[_item(1500)])
    cc = ordens.definir_sem_gasto(
        c["marina"], *(lambda x: (x.id, x.versao))(_sem_itens(c)), "PREVISTO", True
    )
    ordens.iniciar_execucao(c["pedro"], cc.id, cc.versao)
    monkeypatch.setattr(relogio, "agora", lambda: T0 + timedelta(days=1))
    r = relatorios.relatorio_mensal(c["marina"], T0.year, T0.month)
    for bloco in (r.mes_selecionado, r.acumulado):
        assert (bloco.sem_gasto_previstas, bloco.sem_gasto_realizadas) == (2, 1)
        assert bloco.custos.previsto_total_centavos == 1000  # Sem gasto conta como R$ 0
        assert (bloco.custos.concluidas, bloco.custos.previsto_concluidas_centavos) == (2, 1000)
        assert bloco.custos.realizado_concluidas_centavos == 1500
    from osapp.ui.views.relatorio_tempos import texto_sem_gasto

    assert texto_sem_gasto(r.mes_selecionado) == "Sem gasto: 2 previstas, 1 realizada"
    assert date(T0.year, T0.month, 1) <= T0.date()


# --- CLI e migração ----------------------------------------------------------------------


def test_listar_e_marcar_ordens_antigas(c, capsys):
    d = ordens.iniciar_execucao(c["pedro"], *(lambda x: (x.id, x.versao))(_com_item(c)))
    # Simula uma ordem gravada antes do prompt 31: em execução sem item previsto.
    from osapp.models import OsItemCusto

    tabela = OsItemCusto.__table__
    with db.obter_engine().begin() as conexao:
        conexao.execute(tabela.delete().where(tabela.c.os_id == d.id))
    assert cli.main(["listar-sem-itens"]) == 0
    saida = capsys.readouterr().out
    assert f"{d.numero} (EM_EXECUCAO): sem itens no previsto" in saida
    assert "Nada foi alterado" in saida
    assert cli.main(["marcar-sem-gasto", d.numero, "previsto", "--responsavel", "admin"]) == 0
    assert "marcado Sem gasto" in capsys.readouterr().out
    assert ordens.listar_sem_itens() == []
    nao_admin = ["marcar-sem-gasto", d.numero, "previsto", "--responsavel", "marina.teste"]
    assert cli.main(nao_admin) == 1


def test_migracao_0012_com_dados(banco_vazio):
    cfg = config_alembic()
    command.upgrade(cfg, "0011")
    db.reiniciar()
    m = MetaData()
    m.reflect(bind=db.obter_engine())
    t = m.tables
    with db.obter_engine().begin() as conexao:
        conexao.execute(t["filiais"].insert().values(id=1, codigo="1007", nome="Jardinópolis"))
        conexao.execute(
            t["usuarios"]
            .insert()
            .values(id=1, nome="Ana", login="ana", senha_hash="x", filial_id=1, papel="admin")
        )
        conexao.execute(
            t["ordens_servico"]
            .insert()
            .values(
                id=1,
                numero="1007-2026-000001",
                titulo="Antiga",
                descricao="x",
                filial_id=1,
                criado_por_id=1,
                status="EM_EXECUCAO",
                criado_em=T0,
                atualizado_em=T0,
                aberta_em=T0,
                versao=3,
            )
        )
    command.upgrade(cfg, "0012")
    db.reiniciar()
    # Na 0012 o modelo atual (com colunas de migrações posteriores) ainda não serve: lê
    # pelas tabelas refletidas.
    m12 = MetaData()
    m12.reflect(bind=db.obter_engine())
    os12 = m12.tables["ordens_servico"]
    with db.obter_engine().connect() as conexao:
        linha = conexao.execute(
            select(os12.c.sem_gasto_previsto, os12.c.sem_gasto_realizado, os12.c.versao)
        ).one()
    assert (bool(linha[0]), bool(linha[1]), linha[2]) == (False, False, 3)
    command.upgrade(cfg, "head")
    db.reiniciar()
    assert [x.numero for x in ordens.listar_sem_itens()] == ["1007-2026-000001"]
    command.downgrade(cfg, "0011")
    db.reiniciar()
    m = MetaData()
    m.reflect(bind=db.obter_engine())
    assert "sem_gasto_previsto" not in m.tables["ordens_servico"].c
    with db.obter_engine().connect() as conexao:
        numero = select(m.tables["ordens_servico"].c.numero)
        assert conexao.execute(numero).scalars().all() == ["1007-2026-000001"]
    command.upgrade(cfg, "head")
