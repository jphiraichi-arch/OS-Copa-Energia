"""Prompt 17: papéis, fluxo de solicitação, cancelamento e o modelo reduzido do usuario."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import MetaData, event, select

from osapp import cli, db
from osapp.db import sessao
from osapp.models import OrdemServico, Usuario
from osapp.services import administracao, custos, ordens, relogio, status
from osapp.services.erros import (
    ErroAutenticacao,
    ErroNaoEncontrado,
    ErroPermissao,
    ErroValidacao,
)
from tests.conftest import config_alembic
from tests.fabricas import NOTA, categoria_id, itens, tipo_id

SENHA = "senha-ficticia-123"
T0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


class Relogio:
    def __init__(self, monkeypatch):
        self.agora = T0
        monkeypatch.setattr(relogio, "agora", lambda: self.agora)

    def avancar(self, **kw):
        self.agora += timedelta(**kw)


@pytest.fixture
def tempo(monkeypatch):
    return Relogio(monkeypatch)


@pytest.fixture
def pessoas(banco, tempo):
    administracao.criar_filial("1007", "Jardinópolis")
    administracao.criar_filial("2001", "Outra Filial")

    def criar(nome, login, filial, papel):
        return administracao.criar_usuario(nome, login, SENHA, filial, papel=papel).id

    p = {
        "sol": criar("Sônia Solicitante", "sonia.sol", "1007", "usuario"),
        "usu2": criar("Ulisses Usuário", "ulisses.usu", "1007", "usuario"),
        "man": criar("Mário Manutenção", "mario.man", "1007", "manutencao"),
        "man2": criar("Nina Manutenção", "nina.man", "1007", "manutencao"),
        "man_f2": criar("Otto Outra", "otto.outra", "2001", "manutencao"),
        "usu_f2": criar("Paula Outra", "paula.outra", "2001", "usuario"),
        "admin": criar("Ana Admin", "ana.admin", "1007", "admin"),
        "inativo": criar("Ivo Inativo", "ivo.inativo", "1007", "usuario"),
    }
    administracao.desativar_usuario("ivo.inativo")
    return p


def completar(p, os_id):
    """A manutenção completa o previsto de uma solicitação (para poder iniciar)."""
    d = ordens.obter_os(p["man"], os_id)
    d = ordens.editar_os(
        p["man"],
        os_id,
        d.versao,
        {
            "tempo_previsto_minutos": 60,
            "tipo_id": tipo_id(),
            "prioridade": "media",
        },
    )
    return custos.adicionar_item(
        p["man"], os_id, d.versao, "PREVISTO", categoria_id(), "Peça", Decimal("1"), 1000
    )


def concluir(ator, d, nota=NOTA, realizado=True):
    return ordens.concluir_os(
        ator,
        d.id,
        d.versao,
        itens(1500) if realizado else [],
        T0 - timedelta(hours=2),
        T0 - timedelta(hours=1),
        "Feito.",
        nota,
    )


def solicitacao(p, destino=status.ABERTA, urgencia="alta"):
    """Solicitação de 'sol' (1007) levada até ``destino`` pela manutenção 'man'."""
    v = ordens.criar_solicitacao(p["sol"], "Lâmpada queimada", "Corredor B.", urgencia)
    d = completar(p, v.id)
    if destino in (status.EM_EXECUCAO, status.CONCLUIDA):
        d = ordens.iniciar_execucao(p["man"], d.id, d.versao)
    if destino == status.CONCLUIDA:
        d = concluir(p["man"], d)
    if destino == status.CANCELADA:
        d = ordens.cancelar(p["sol"], d.id, d.versao)
    assert d.status == destino
    return ordens.obter_os(p["admin"], d.id)


# --- Matriz papel x ação x status ------------------------------------------------------

ATORES = ["sol", "usu2", "man", "man2", "man_f2", "admin", "inativo"]
#          solicitante, outro usuario, manutenção executora, outra manutenção da filial,
#          manutenção de outra filial, administrador, usuário inativo
OK, PERM, NE, AUT = "ok", ErroPermissao, ErroNaoEncontrado, ErroAutenticacao
A, E, C, X = status.ABERTA, status.EM_EXECUCAO, status.CONCLUIDA, status.CANCELADA
MATRIZ = {
    ("editar_solicitacao", A): [OK, PERM, PERM, PERM, NE, OK, AUT],
    ("editar_solicitacao", E): [PERM, PERM, PERM, PERM, NE, OK, AUT],
    ("editar_solicitacao", C): [PERM, PERM, PERM, PERM, NE, OK, AUT],
    ("editar_solicitacao", X): [PERM, PERM, PERM, PERM, NE, PERM, AUT],
    ("editar_os", A): [PERM, PERM, OK, OK, NE, OK, AUT],
    ("editar_os", E): [PERM, PERM, OK, OK, NE, OK, AUT],
    ("editar_os", C): [PERM, PERM, PERM, PERM, NE, OK, AUT],
    ("editar_os", X): [PERM, PERM, PERM, PERM, NE, PERM, AUT],
    ("iniciar", A): [PERM, PERM, OK, OK, NE, OK, AUT],
    ("iniciar", E): [PERM, PERM, PERM, PERM, NE, PERM, AUT],
    ("iniciar", C): [PERM, PERM, PERM, PERM, NE, PERM, AUT],
    ("iniciar", X): [PERM, PERM, PERM, PERM, NE, PERM, AUT],
    ("desfazer", A): [PERM, PERM, PERM, PERM, NE, PERM, AUT],
    ("desfazer", E): [PERM, PERM, OK, PERM, NE, OK, AUT],
    ("desfazer", C): [PERM, PERM, PERM, PERM, NE, PERM, AUT],
    ("desfazer", X): [PERM, PERM, PERM, PERM, NE, PERM, AUT],
    ("concluir", A): [PERM, PERM, PERM, PERM, NE, PERM, AUT],
    ("concluir", E): [PERM, PERM, OK, PERM, NE, OK, AUT],
    ("concluir", C): [PERM, PERM, PERM, PERM, NE, PERM, AUT],
    ("concluir", X): [PERM, PERM, PERM, PERM, NE, PERM, AUT],
    ("cancelar", A): [OK, PERM, PERM, PERM, NE, OK, AUT],
    ("cancelar", E): [PERM, PERM, PERM, PERM, NE, PERM, AUT],
    ("cancelar", C): [PERM, PERM, PERM, PERM, NE, PERM, AUT],
    ("cancelar", X): [PERM, PERM, PERM, PERM, NE, PERM, AUT],
}
CELULAS = [
    (ator, acao, st, MATRIZ[(acao, st)][i])
    for (acao, st) in MATRIZ
    for i, ator in enumerate(ATORES)
]
# Flag de acoes que corresponde a cada ação (modelo completo; o do usuario tem os mesmos
# nomes, com pode_editar = editar_solicitacao, e não tem flag de editar_os).
FLAG_COMPLETO = {
    "editar_solicitacao": "pode_editar_solicitacao",
    "editar_os": "pode_editar",
    "iniciar": "pode_iniciar",
    "desfazer": "pode_desfazer_inicio",
    "concluir": "pode_concluir",
    "cancelar": "pode_cancelar",
}
FLAG_USUARIO = {**FLAG_COMPLETO, "editar_solicitacao": "pode_editar", "editar_os": None}


def executar(acao, ator, d):
    if acao == "editar_solicitacao":
        return ordens.editar_solicitacao(ator, d.id, d.versao, {"titulo": "Título novo"})
    if acao == "editar_os":
        return ordens.editar_os(ator, d.id, d.versao, {"prioridade": "alta"})
    if acao == "iniciar":
        return ordens.iniciar_execucao(ator, d.id, d.versao)
    if acao == "desfazer":
        return ordens.desfazer_inicio(ator, d.id, d.versao)
    if acao == "concluir":
        return concluir(ator, d)
    return ordens.cancelar(ator, d.id, d.versao)


def foto(os_id):
    with sessao() as s:
        o = s.get(OrdemServico, os_id)
        return (o.status, o.versao, o.titulo, o.prioridade, o.executor_id, o.cancelada_em)


def test_tamanho_da_matriz():
    assert len(CELULAS) == 7 * 6 * 4 == 168


@pytest.mark.parametrize(
    ("ator", "acao", "st", "esperado"), CELULAS, ids=[f"{a}-{c}-{s}" for a, c, s, _ in CELULAS]
)
def test_matriz(pessoas, ator, acao, st, esperado):
    d = solicitacao(pessoas, st)
    antes = foto(d.id)
    if esperado in (OK, PERM):
        visto = ordens.obter_os(pessoas[ator], d.id)
        usuario = isinstance(visto, ordens.OsVisaoSolicitante)
        nome = (FLAG_USUARIO if usuario else FLAG_COMPLETO)[acao]
        if nome is not None:
            assert getattr(visto.acoes, nome) is (esperado == OK)
    if esperado == OK:
        depois = executar(acao, pessoas[ator], d)
        assert depois.versao > d.versao and foto(d.id) != antes
    else:
        with pytest.raises(esperado):
            executar(acao, pessoas[ator], d)
        assert foto(d.id) == antes


# --- O usuario não recebe nem carrega dados restritos --------------------------------

PERMITIDOS_USUARIO = {
    "id",
    "numero",
    "versao",
    "titulo",
    "descricao",
    "urgencia",
    "status",
    "solicitante",
    "filial_codigo",
    "aberta_em",
    "inicio_execucao_em",
    "concluida_em",
    "cancelada_em",
    "nota_conclusao",
    "acoes",
    "pode_editar",
    "pode_cancelar",
    "pode_iniciar",
    "pode_desfazer_inicio",
    "pode_concluir",
    "itens",
    "tem_mais",
}
PROIBIDOS = (
    "previsto",
    "realizado",
    "custo",
    "valor",
    "tipo",
    "prioridade",
    "executor",
    "evento",
    "sap",
    "concluido_por",
    "tempo",
)


def chaves(objeto) -> set[str]:
    """Todos os nomes de campo de um objeto devolvido, recursivamente."""
    nomes = set()
    if dataclasses.is_dataclass(objeto):
        for campo in dataclasses.fields(objeto):
            nomes.add(campo.name)
            nomes |= chaves(getattr(objeto, campo.name))
    elif isinstance(objeto, list | tuple):
        for item in objeto:
            nomes |= chaves(item)
    return nomes


def test_usuario_so_recebe_campos_permitidos(pessoas):
    concluida = solicitacao(pessoas, status.CONCLUIDA)
    nova = ordens.criar_solicitacao(pessoas["sol"], "Torneira", "Pingando.", "baixa")
    editada = ordens.editar_solicitacao(pessoas["sol"], nova.id, nova.versao, {"urgencia": "media"})
    cancelada = ordens.cancelar(pessoas["sol"], editada.id, editada.versao)
    recebidos = [
        nova,
        editada,
        cancelada,
        ordens.obter_os(pessoas["sol"], concluida.id),
        ordens.obter_os(pessoas["usu2"], concluida.id),
        ordens.listar_os(pessoas["sol"]),
        ordens.listar_os(pessoas["sol"], busca="Lâmpada"),
        ordens.listar_os(pessoas["sol"], status=status.CONCLUIDA),
    ]
    for objeto in recebidos:
        nomes = chaves(objeto)
        assert nomes <= PERMITIDOS_USUARIO, nomes - PERMITIDOS_USUARIO
        texto = " ".join(sorted(nomes))
        for proibido in PROIBIDOS:
            assert proibido not in texto
    assert ordens.obter_os(pessoas["sol"], concluida.id).nota_conclusao == NOTA
    with pytest.raises(ErroPermissao):
        ordens.listar_eventos(pessoas["sol"], concluida.id)
    with pytest.raises(ErroPermissao):
        ordens.listar_tipos(pessoas["sol"])


def test_consulta_do_usuario_nem_le_colunas_restritas(pessoas):
    d = solicitacao(pessoas, status.CONCLUIDA)
    comandos: list[str] = []

    def guardar(_con, _cursor, sql, *_args):
        comandos.append(sql.lower())

    engine = db.obter_engine()
    event.listen(engine, "before_cursor_execute", guardar)
    try:
        ordens.obter_os(pessoas["sol"], d.id)
        ordens.listar_os(pessoas["sol"])
        ordens.listar_os(pessoas["sol"], busca=d.numero)
    finally:
        event.remove(engine, "before_cursor_execute", guardar)
    consultas_de_os = [c for c in comandos if "ordens_servico" in c]
    assert consultas_de_os
    for sql in consultas_de_os:
        for coluna in (
            "os_itens_custo",
            "tempo_previsto",
            "prioridade",
            "tipo_id",
            "executor_id",
            "realizado",
            "numero_sap",
            "os_eventos",
        ):
            assert coluna not in sql, (coluna, sql)


# --- Visibilidade -------------------------------------------------------------------


def test_usuario_ve_toda_a_filial_e_nada_de_outra(pessoas):
    da_manutencao = ordens.criar_os(pessoas["man"], "Preventiva bomba", "Plano mensal.")
    de_outro = ordens.criar_solicitacao(pessoas["usu2"], "Janela", "Quebrada.", "media")
    propria = ordens.criar_solicitacao(pessoas["sol"], "Porta", "Range.", "baixa")
    outra_filial = ordens.criar_solicitacao(pessoas["usu_f2"], "Telhado", "Goteira.", "alta")
    vistos = {i.numero for i in ordens.listar_os(pessoas["sol"]).itens}
    assert vistos == {da_manutencao.numero, de_outro.numero, propria.numero}
    assert ordens.listar_os(pessoas["sol"], busca=outra_filial.numero).itens == ()
    with pytest.raises(ErroNaoEncontrado):
        ordens.obter_os(pessoas["sol"], outra_filial.id)
    with pytest.raises(ErroPermissao):
        ordens.listar_os(pessoas["sol"], filial_id=2)
    # Os dois usuários enxergam a solicitação de origem manutenção, no modelo reduzido.
    visto = ordens.obter_os(pessoas["sol"], da_manutencao.id)
    assert isinstance(visto, ordens.OsVisaoSolicitante) and visto.urgencia is None
    # Manutenção de outra filial não vê nada da 1007; o administrador vê tudo.
    assert {i.numero for i in ordens.listar_os(pessoas["man_f2"]).itens} == {outra_filial.numero}
    with pytest.raises(ErroNaoEncontrado):
        ordens.obter_os(pessoas["man_f2"], propria.id)
    assert len(ordens.listar_os(pessoas["admin"]).itens) == 4


def test_busca_do_usuario_e_por_numero_titulo_e_descricao(pessoas):
    d = ordens.criar_solicitacao(pessoas["sol"], "Ar-condicionado", "Sala 3 sem gelar.", "alta")
    for termo in (d.numero, "condicionado", "sala 3"):
        assert [i.id for i in ordens.listar_os(pessoas["usu2"], busca=termo).itens] == [d.id]
    assert ordens.listar_os(pessoas["usu2"], busca="Sônia").itens == ()  # nome não entra


# --- Criação -------------------------------------------------------------------------


def test_criar_solicitacao_qualquer_papel_e_filial_travada(pessoas):
    for ator in ("sol", "man", "admin"):
        d = ordens.criar_solicitacao(pessoas[ator], "Título ok", "Descrição.", "media")
        assert d.status == status.ABERTA and d.numero.startswith("1007-2026-")
    v = ordens.obter_os(pessoas["admin"], d.id)
    assert (v.origem, v.urgencia, v.aberta_em, v.prioridade) == ("solicitacao", "media", T0, None)
    with pytest.raises(ErroPermissao):
        ordens.criar_solicitacao(pessoas["sol"], "Título ok", "Descrição.", "media", 2)
    outra = ordens.criar_solicitacao(pessoas["admin"], "Título ok", "Descrição.", "media", 2)
    assert outra.filial_codigo == "2001"
    for urgencia in (None, "", "urgente", "MEDIA"):
        with pytest.raises(ErroValidacao) as info:
            ordens.criar_solicitacao(pessoas["sol"], "Título ok", "Descrição.", urgencia)
        assert info.value.campo == "urgencia"
    with pytest.raises(ErroAutenticacao):
        ordens.criar_solicitacao(pessoas["inativo"], "Título ok", "Descrição.", "media")


def test_criar_os_completa_so_manutencao_e_admin(pessoas):
    with pytest.raises(ErroPermissao):
        ordens.criar_os(pessoas["sol"], "Título ok", "Descrição.")
    d = ordens.criar_os(pessoas["man"], "Título ok", "Descrição.")
    assert (d.origem, d.urgencia, d.tempo_previsto_minutos, d.itens) == (
        "manutencao",
        None,
        None,
        (),
    )
    assert d.acoes.pode_iniciar is False and len(d.pendencias_para_iniciar) == 4


# --- Previsto completo, conclusão, cancelamento, desfazer ---------------------------


@pytest.mark.parametrize(
    ("falta", "pendencia"),
    [
        ("tempo", ordens.PENDENCIA_TEMPO),
        ("itens", ordens.PENDENCIA_VALOR),
        ("tipo", ordens.PENDENCIA_TIPO),
        ("prioridade", ordens.PENDENCIA_PRIORIDADE),
    ],
)
def test_iniciar_exige_o_previsto_completo(pessoas, falta, pendencia):
    dados = {
        "tempo_previsto_minutos": 60,
        "itens_previstos": itens(1000),
        "tipo_id": tipo_id(),
        "prioridade": "media",
    }
    chave = {
        "tempo": "tempo_previsto_minutos",
        "itens": "itens_previstos",
        "tipo": "tipo_id",
        "prioridade": "prioridade",
    }[falta]
    dados.pop(chave)
    d = ordens.criar_os(pessoas["man"], "Título ok", "Descrição.", **dados)
    assert d.pendencias_para_iniciar == (pendencia,) and not d.acoes.pode_iniciar
    with pytest.raises(ErroValidacao) as info:
        ordens.iniciar_execucao(pessoas["man"], d.id, d.versao)
    assert info.value.campo == "previsto" and pendencia in info.value.mensagem
    assert foto(d.id)[0] == status.ABERTA


@pytest.mark.parametrize("nota", [None, "", "    ", "abcd", "x" * 501, "texto\x00ruim"])
def test_concluir_exige_nota_valida(pessoas, nota):
    d = solicitacao(pessoas, status.EM_EXECUCAO)
    with pytest.raises(ErroValidacao) as info:
        concluir(pessoas["man"], d, nota=nota)
    assert info.value.campo == "nota_conclusao"
    assert foto(d.id)[0] == status.EM_EXECUCAO


def test_concluir_exige_realizado_e_guarda_nota_aparada(pessoas, tempo):
    d = solicitacao(pessoas, status.EM_EXECUCAO)
    with pytest.raises(ErroValidacao):
        concluir(pessoas["man"], d, realizado=False)
    for limite in ("abcde", "y" * 500):
        assert len(limite) in (5, 500)
    c = concluir(pessoas["man"], d, nota="  Troquei a lâmpada.  ")
    assert (c.status, c.nota_conclusao, c.concluida_em) == (
        status.CONCLUIDA,
        "Troquei a lâmpada.",
        T0,
    )


def test_cancelar_e_final(pessoas, tempo):
    d = solicitacao(pessoas, status.ABERTA)
    tempo.avancar(minutes=7)
    v = ordens.cancelar(pessoas["sol"], d.id, d.versao)
    assert isinstance(v, ordens.OsVisaoSolicitante)
    assert (v.status, v.cancelada_em) == (status.CANCELADA, T0 + timedelta(minutes=7))
    completo = ordens.obter_os(pessoas["admin"], d.id)
    assert completo.cancelada_por_nome == "Sônia Solicitante"
    acoes = completo.acoes
    assert not any(
        (
            acoes.pode_editar,
            acoes.pode_iniciar,
            acoes.pode_concluir,
            acoes.pode_cancelar,
            acoes.pode_editar_solicitacao,
            acoes.pode_editar_itens_previstos,
        )
    )
    for chamada in (
        lambda: ordens.iniciar_execucao(pessoas["admin"], d.id, completo.versao),
        lambda: ordens.editar_os(pessoas["admin"], d.id, completo.versao, {"prioridade": "alta"}),
        lambda: ordens.editar_solicitacao(
            pessoas["admin"], d.id, completo.versao, {"titulo": "Outro"}
        ),
        lambda: concluir(pessoas["admin"], completo),
        lambda: custos.adicionar_item(
            pessoas["admin"],
            d.id,
            completo.versao,
            "PREVISTO",
            categoria_id(),
            "X",
            Decimal("1"),
            1,
        ),
    ):
        with pytest.raises(ErroPermissao):
            chamada()


def test_desfazer_apaga_o_inicio_e_novo_inicio_grava_outro(pessoas, tempo):
    d = solicitacao(pessoas, status.ABERTA)
    tempo.avancar(hours=1)
    d = ordens.iniciar_execucao(pessoas["man"], d.id, d.versao)
    assert d.inicio_execucao_em == T0 + timedelta(hours=1)
    tempo.avancar(hours=1)
    d = ordens.desfazer_inicio(pessoas["man"], d.id, d.versao)
    assert (d.status, d.inicio_execucao_em, d.executor_id) == (status.ABERTA, None, None)
    tempo.avancar(hours=1)
    d = ordens.iniciar_execucao(pessoas["man2"], d.id, d.versao)
    assert (d.inicio_execucao_em, d.executor_nome) == (T0 + timedelta(hours=3), "Nina Manutenção")
    tipos = [
        e.valor_novo for e in ordens.listar_eventos(pessoas["admin"], d.id) if e.tipo == "STATUS"
    ]
    assert tipos == ["EM_EXECUCAO", "ABERTA", "EM_EXECUCAO"]  # o histórico guarda tudo


# --- Instantes de status ------------------------------------------------------------


def test_cada_transicao_grava_exatamente_o_instante_do_relogio(pessoas, tempo):
    v = ordens.criar_solicitacao(pessoas["sol"], "Título ok", "Descrição.", "alta")
    d = completar(pessoas, v.id)
    tempo.avancar(minutes=30)
    d = ordens.iniciar_execucao(pessoas["man"], d.id, d.versao)
    tempo.avancar(minutes=45)
    d = concluir(pessoas["man"], d)
    assert (d.aberta_em, d.inicio_execucao_em, d.concluida_em, d.cancelada_em) == (
        T0,
        T0 + timedelta(minutes=30),
        T0 + timedelta(minutes=75),
        None,
    )


@pytest.mark.parametrize(
    "campo",
    [
        "aberta_em",
        "inicio_execucao_em",
        "concluida_em",
        "cancelada_em",
        "cancelada_por_id",
        "nota_conclusao",
        "status",
        "executor_id",
        "origem",
        "urgencia",
    ],
)
def test_instantes_e_campos_de_status_nunca_vem_da_entrada(pessoas, campo):
    d = solicitacao(pessoas, status.ABERTA)
    for ator in ("man", "admin"):
        with pytest.raises(ErroPermissao):
            ordens.editar_os(pessoas[ator], d.id, d.versao, {campo: T0})
    if campo != "urgencia":
        with pytest.raises(ErroPermissao):
            ordens.editar_solicitacao(pessoas["sol"], d.id, d.versao, {campo: T0})
    assert foto(d.id)[1] == d.versao


def test_manutencao_nunca_muda_urgencia_e_usuario_nao_mexe_em_itens(pessoas):
    d = solicitacao(pessoas, status.ABERTA)
    with pytest.raises(ErroPermissao):
        ordens.editar_solicitacao(pessoas["man"], d.id, d.versao, {"urgencia": "baixa"})
    with pytest.raises(ErroPermissao):
        custos.adicionar_item(
            pessoas["sol"], d.id, d.versao, "PREVISTO", categoria_id(), "X", Decimal("1"), 1
        )
    a = ordens.editar_solicitacao(pessoas["admin"], d.id, d.versao, {"urgencia": "baixa"})
    assert a.urgencia == "baixa"


def test_titulo_de_solicitacao_nao_e_editado_pela_manutencao(pessoas):
    d = solicitacao(pessoas, status.ABERTA)
    with pytest.raises(ErroPermissao):
        ordens.editar_os(pessoas["man"], d.id, d.versao, {"titulo": "Outro título"})
    m = ordens.criar_os(pessoas["man"], "Título ok", "Descrição.")
    m = ordens.editar_os(pessoas["man2"], m.id, m.versao, {"titulo": "Outro título"})
    assert m.titulo == "Outro título"


# --- CLI ----------------------------------------------------------------------------


def test_cli_criar_usuario_com_papel_e_reclassificar_origem(pessoas, monkeypatch, capsys):
    monkeypatch.setattr(cli.getpass, "getpass", lambda _p="": SENHA)
    argumentos = ["criar-usuario", "--nome", "Rui", "--login", "rui.usu", "--filial", "1007"]
    assert cli.main([*argumentos, "--papel", "usuario"]) == 0
    with sessao() as s:
        assert s.scalars(select(Usuario.papel).where(Usuario.login == "rui.usu")).one() == (
            "usuario"
        )
    d = ordens.criar_os(pessoas["man"], "Antiga", "Era um pedido.")
    capsys.readouterr()
    base = ["reclassificar-origem", d.numero, "solicitacao"]
    assert cli.main([*base, "--responsavel", "ana.admin"]) == 0
    assert "prévia" in capsys.readouterr().out
    assert ordens.obter_os(pessoas["admin"], d.id).origem == "manutencao"
    assert cli.main([*base, "--responsavel", "mario.man", "--aplicar"]) == 1  # não é admin
    assert cli.main([*base, "--responsavel", "ana.admin", "--aplicar"]) == 0
    depois = ordens.obter_os(pessoas["admin"], d.id)
    assert depois.origem == "solicitacao" and depois.versao == d.versao + 1
    assert ordens.listar_eventos(pessoas["admin"], d.id)[-1].campo == "origem"


# --- Migração 0008 ------------------------------------------------------------------


def _tabelas():
    db.reiniciar()
    tabelas = MetaData()
    tabelas.reflect(bind=db.obter_engine())
    return tabelas.tables


def test_migracao_0008_com_dados_ida_e_volta(banco_vazio):
    cfg = config_alembic()
    command.upgrade(cfg, "0007")
    t = _tabelas()
    h = timedelta(hours=1)
    with db.obter_engine().begin() as conexao:
        conexao.execute(t["filiais"].insert().values(id=1, codigo="1007", nome="Jardinópolis"))
        for linha in (
            dict(
                id=1,
                nome="Admin",
                login="admin",
                senha_hash="x",
                filial_id=1,
                is_admin=True,
                papel="admin",
            ),
            # gravado pelo código antigo depois da 0007: is_admin sem papel
            dict(
                id=2,
                nome="Novo Admin",
                login="novo.admin",
                senha_hash="x",
                filial_id=1,
                is_admin=True,
                papel="manutencao",
            ),
            dict(
                id=3, nome="Marina", login="marina", senha_hash="x", filial_id=1, papel="manutencao"
            ),
        ):
            conexao.execute(t["usuarios"].insert().values(**linha))
        base = dict(
            filial_id=1,
            criado_por_id=3,
            titulo="T",
            descricao="D",
            tempo_previsto_minutos=60,
            atualizado_em=T0,
            versao=1,
            criado_em=T0,
        )
        for linha in (
            dict(base, id=1, numero="1007-2026-000001", status="ABERTA", aberta_em=T0 + h),
            dict(
                base,
                id=2,
                numero="1007-2026-000002",
                status="EM_EXECUCAO",
                aberta_em=T0,
                iniciado_em=T0 + h,
                executor_id=3,
            ),
            dict(
                base,
                id=3,
                numero="1007-2026-000003",
                status="CONCLUIDA",
                aberta_em=T0,
                iniciado_em=T0 + h,
                concluido_em=T0 + 2 * h,
                executor_id=3,
                concluido_por_id=3,
            ),
        ):
            conexao.execute(t["ordens_servico"].insert().values(**linha))
    db.reiniciar()

    command.upgrade(cfg, "0008")
    t = _tabelas()
    assert "is_admin" not in t["usuarios"].c and "iniciado_em" not in t["ordens_servico"].c
    with db.obter_engine().connect() as conexao:
        papeis = dict(conexao.execute(select(t["usuarios"].c.login, t["usuarios"].c.papel)).all())
        os_ = {linha.id: linha for linha in conexao.execute(select(t["ordens_servico"])).all()}
    assert papeis == {"admin": "admin", "novo.admin": "admin", "marina": "manutencao"}
    agora = {k: (v.aberta_em, v.inicio_execucao_em, v.concluida_em) for k, v in os_.items()}

    def utc(x):
        return None if x is None else x.replace(tzinfo=UTC)

    assert {k: tuple(utc(x) for x in v) for k, v in agora.items()} == {
        1: (T0, None, None),
        2: (T0, T0 + h, None),
        3: (T0, T0 + h, T0 + 2 * h),
    }

    command.downgrade(cfg, "0007")
    t = _tabelas()
    with db.obter_engine().connect() as conexao:
        admins = dict(
            conexao.execute(select(t["usuarios"].c.login, t["usuarios"].c.is_admin)).all()
        )
        tempos = dict(
            conexao.execute(
                select(t["ordens_servico"].c.id, t["ordens_servico"].c.concluido_em)
            ).all()
        )
    assert admins == {"admin": True, "novo.admin": True, "marina": False}
    assert utc(tempos[3]) == T0 + 2 * h and tempos[1] is None
    command.upgrade(cfg, "head")
