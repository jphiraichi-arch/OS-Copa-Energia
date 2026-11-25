"""Prompt 41: Sem gasto na criação, seção de itens única, exibição das fases, pendências,
contadores, motivo de cancelamento, preparar-piloto e barra inferior."""

from __future__ import annotations

import builtins
import itertools
import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from osapp import cli
from osapp.db import sessao
from osapp.models import (
    CategoriaCusto,
    Especialidade,
    Filial,
    MotivoCancelamento,
    OrdemServico,
    OsEvento,
    SlaAlvo,
    TipoManutencao,
    Usuario,
)
from osapp.services import administracao, custos, ordens, piloto, relogio
from osapp.services.erros import ErroValidacao
from osapp.ui import fase_custo, theme
from osapp.ui.components.barra_inferior import BarraInferior, altura
from osapp.ui.components.editor_itens import EditorItens, EstadoFase, SecaoItensCusto
from tests.fabricas import categoria_id, especialidade_id, itens, motivo_id, tipo_id

SENHA = "senha-ficticia-123"
T0 = datetime(2026, 11, 25, 13, 0, tzinfo=UTC)


@pytest.fixture
def p(banco, monkeypatch):
    monkeypatch.setattr(relogio, "agora", lambda: T0)
    administracao.criar_filial("1007", "Jardinópolis")

    def criar(nome, login, papel):
        return administracao.criar_usuario(nome, login, SENHA, "1007", papel=papel).id

    return {
        "admin": criar("Ana Admin", "ana.admin", "admin"),
        "man": criar("Mário", "mario.man", "manutencao"),
        "sol": criar("Sônia", "sonia.sol", "usuario"),
    }


COMPLETO = {"tempo_previsto_minutos": 60, "prioridade": "media"}


# --- Sem gasto na criação -----------------------------------------------------------------


def test_criar_com_sem_gasto_e_iniciar_sem_abrir_alterar(p):
    d = ordens.criar_os(
        p["man"],
        "Troca de lâmpada",
        "Sem custo.",
        [],
        60,
        tipo_id=tipo_id(),
        prioridade="media",
        especialidade_id=especialidade_id(),
        sem_gasto_previsto=True,
    )
    assert d.sem_gasto_previsto and d.pendencias_para_iniciar == () and d.acoes.pode_iniciar
    assert ordens.iniciar_execucao(p["man"], d.id, d.versao).status == "EM_EXECUCAO"
    campos = [e.campo for e in ordens.listar_eventos(p["man"], d.id)]
    assert "sem_gasto_previsto" in campos


def test_criar_com_sem_gasto_e_itens_e_recusado(p):
    with pytest.raises(ErroValidacao) as erro:
        ordens.criar_os(p["man"], "Título ok", "Desc.", itens(1000), sem_gasto_previsto=True)
    assert erro.value.mensagem == ordens.MSG_SEM_GASTO_COM_ITENS


# --- Seção de itens: a mesma lógica nas três telas -------------------------------------------


def test_uma_so_secao_de_itens():
    assert SecaoItensCusto is EditorItens


@pytest.mark.parametrize("tela", ["nova_os", "alterar", "concluir"])
def test_estado_da_fase_igual_nas_tres_telas(tela):
    e = EstadoFase()
    assert e.marcar(True) == "aplicado" and e.sem_gasto and not e.pode_adicionar
    assert e.marcar(False) == "aplicado" and not e.sem_gasto and e.pode_adicionar
    e.adicionar()
    assert e.n_itens == 1 and not e.sem_gasto
    e.sem_gasto = True
    e.adicionar()  # incluir item desmarca
    assert not e.sem_gasto and e.coerente
    assert e.marcar(True) == "confirmar" and not e.sem_gasto  # com itens: pergunta antes
    e.trocar_por_sem_gasto()
    assert (e.n_itens, e.sem_gasto, e.coerente) == (0, True, True)
    assert not EstadoFase(n_itens=2, sem_gasto=True).coerente  # os dois juntos: inválido


# --- Exibição da fase ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tem_itens", "sem_gasto", "total", "pill", "texto_total", "lista"),
    [
        (False, False, 0, "A DEFINIR", "—", "—"),
        (False, True, 0, "SEM GASTO", "SEM GASTO", "Sem gasto"),
        (True, False, 12345, "R$ 123,45", "R$ 123,45", "R$ 123,45"),
        (True, False, 0, "R$ 0,00", "R$ 0,00", "R$ 0,00"),
    ],
)
def test_exibicao_da_fase(tem_itens, sem_gasto, total, pill, texto_total, lista):
    e = fase_custo.exibicao(tem_itens, sem_gasto, total)
    assert (e.pill, e.total) == (pill, texto_total)
    assert fase_custo.texto_da_lista(tem_itens, sem_gasto, total) == lista


def test_lista_traz_o_que_precisa_para_o_custo(p):
    vazia = ordens.criar_os(p["man"], "Sem nada", "Desc.", [])
    marcada = ordens.criar_os(p["man"], "Marcada", "Desc.", [], sem_gasto_previsto=True)
    por_id = {o.id: o for o in ordens.listar_os(p["man"]).itens}
    assert (por_id[vazia.id].tem_itens_previstos, por_id[vazia.id].sem_gasto_previsto) == (
        False,
        False,
    )
    assert por_id[marcada.id].sem_gasto_previsto


# --- Pendências: a tela e o serviço nunca discordam ----------------------------------------


CAMPOS = ("tempo", "custo", "tipo", "prioridade", "especialidade")


@pytest.mark.parametrize("faltam", list(itertools.combinations(CAMPOS, 2)) + [()])
def test_pendencias_inicio_e_iniciar_concordam(p, faltam):
    kwargs = {
        "tipo_id": None if "tipo" in faltam else tipo_id(),
        "prioridade": None if "prioridade" in faltam else "media",
        "especialidade_id": None if "especialidade" in faltam else especialidade_id(),
    }
    d = ordens.criar_os(
        p["man"],
        "Ordem",
        "Desc.",
        [] if "custo" in faltam else itens(1000),
        None if "tempo" in faltam else 60,
        **kwargs,
    )
    with sessao() as s:
        pend = ordens.pendencias_inicio(s.get(OrdemServico, d.id))
    assert pend == d.pendencias_para_iniciar
    assert len(pend) == len(faltam)
    assert d.acoes.iniciar_bloqueado == bool(pend) and d.acoes.pode_iniciar == (not pend)
    if pend:
        with pytest.raises(ErroValidacao):
            ordens.iniciar_execucao(p["man"], d.id, d.versao)
    else:
        assert ordens.iniciar_execucao(p["man"], d.id, d.versao).status == "EM_EXECUCAO"


def test_texto_das_pendencias():
    from osapp.ui.views.detalhe import texto_pendencias

    assert texto_pendencias(("tempo previsto", "especialidade")) == (
        "Para iniciar, falta: tempo previsto, especialidade."
    )


# --- Contadores ---------------------------------------------------------------------------


def test_contadores_abertas_e_em_execucao(p):
    a = ordens.criar_solicitacao(p["sol"], "Aberta 1", "Desc.", "alta")
    ordens.criar_solicitacao(p["sol"], "Aberta 2", "Desc.", "baixa")
    d = ordens.obter_os(p["man"], a.id)
    d = ordens.editar_os(
        p["man"],
        d.id,
        d.versao,
        {**COMPLETO, "tipo_id": tipo_id(), "especialidade_id": especialidade_id()},
    )
    d = custos.adicionar_item(
        p["man"], d.id, d.versao, "PREVISTO", categoria_id(), "Peça", Decimal("1"), 500
    )
    ordens.iniciar_execucao(p["man"], d.id, d.versao)
    c = ordens.contadores(p["man"])
    assert (c.abertas, c.em_execucao) == (1, 1)
    assert not hasattr(c, "aguardando_inicio")


# --- Motivo de cancelamento ---------------------------------------------------------------


def test_cancelamento_exige_motivo_e_outro_exige_texto(p):
    v = ordens.criar_solicitacao(p["sol"], "Computador lento", "Desc.", "baixa")
    with pytest.raises(ErroValidacao) as erro:
        ordens.cancelar(p["sol"], v.id, v.versao)
    assert erro.value.campo == "motivo_cancelamento_id"
    for texto in (None, "", "abc"):
        with pytest.raises(ErroValidacao) as erro:
            ordens.cancelar(p["sol"], v.id, v.versao, motivo_id("OUTRO"), texto)
        assert erro.value.campo == "motivo_cancelamento_texto"
    c = ordens.cancelar(p["sol"], v.id, v.versao, motivo_id("OUTRO"), "Pedido refeito por telefone")
    assert c.motivo_cancelamento == "Outro: Pedido refeito por telefone"
    assert (
        ordens.obter_os(p["admin"], v.id).motivo_cancelamento
        == "Outro: Pedido refeito por telefone"
    )
    with sessao() as s:
        o = s.get(OrdemServico, v.id)
        assert o.motivo_cancelamento.codigo == "OUTRO"
        observacoes = list(s.scalars(select(OsEvento.observacao).where(OsEvento.os_id == v.id)))
    assert "Motivo: Outro - Pedido refeito por telefone" in observacoes


def test_motivos_iniciais_e_fora_do_escopo_primeiro(p):
    from osapp.services import motivos_cancelamento

    nomes = [m.nome for m in motivos_cancelamento.listar(p["sol"])]
    assert nomes == ["Fora do escopo (TI)", "Duplicada", "Aberta por engano", "Outro"]


def test_dica_de_escopo_na_nova_solicitacao():
    from osapp.ui.views.solicitacao import NovaSolicitacao

    assert NovaSolicitacao.dica_titulo == (
        "Problemas de computador, rede ou sistemas: abrir chamado com a TI."
    )


# --- preparar-piloto ----------------------------------------------------------------------


def _contar(modelo) -> int:
    with sessao() as s:
        return s.scalar(select(func.count()).select_from(modelo))


def test_preparar_piloto_recusa_sem_flag_e_sem_confirmacao(p, monkeypatch, capsys):
    ordens.criar_solicitacao(p["sol"], "Teste", "Desc.", "baixa")
    assert cli.main(["preparar-piloto"]) == 1  # sem --confirmar: só o plano
    assert "BACKUP" in capsys.readouterr().out
    monkeypatch.setattr(builtins, "input", lambda _p="": "outro-banco")
    assert cli.main(["preparar-piloto", "--confirmar"]) == 1
    monkeypatch.setenv("OS_AMBIENTE", "producao")
    monkeypatch.setattr(builtins, "input", lambda _p="": "teste.db")
    assert cli.main(["preparar-piloto", "--confirmar"]) == 1
    assert _contar(OrdemServico) == 1


def test_preparar_piloto_apaga_reinicia_e_cria_usuarios(p, monkeypatch, capsys):
    from osapp import config

    for i in range(3):
        ordens.criar_solicitacao(p["sol"], f"Teste {i}", "Desc.", "baixa")
    referencias = {
        m: _contar(m)
        for m in (
            Filial,
            CategoriaCusto,
            TipoManutencao,
            Especialidade,
            SlaAlvo,
            MotivoCancelamento,
        )
    }
    banco = config.nome_do_banco(config.carregar_config().database_url)
    monkeypatch.setattr(builtins, "input", lambda _p="": banco)
    assert cli.main(["preparar-piloto", "--confirmar"]) == 0
    saida = capsys.readouterr().out
    assert _contar(OrdemServico) == 0 and _contar(OsEvento) == 0
    assert {m: _contar(m) for m in referencias} == referencias
    with sessao() as s:
        logins = set(s.scalars(select(Usuario.login)))
        novos = {
            u: s.scalars(select(Usuario).where(Usuario.login == u)).one()
            for _n, u, _pp in piloto.USUARIOS_DO_PILOTO
        }
        assert all(u.deve_trocar_senha for u in novos.values())
    assert "ana.admin" in logins  # o administrador existente fica
    papeis = [pp for _n, _u, pp in piloto.USUARIOS_DO_PILOTO]
    assert papeis.count("usuario") >= 2 and papeis.count("manutencao") >= 2
    assert papeis.count("admin") >= 1
    for _nome, login, _papel in piloto.USUARIOS_DO_PILOTO:
        assert re.fullmatch(r"[a-z]+\.[a-z]+", login)
        assert not re.search(r"usuario|manutencao|admin|teste|\d", login)
        assert login in saida  # a senha temporária aparece uma vez, com o login
    # A numeração recomeça.
    nova = ordens.criar_solicitacao(p["sol"], "Primeira do piloto", "Desc.", "alta")
    assert nova.numero.endswith("-000001")
    # Idempotente: rodar de novo não duplica.
    assert cli.main(["preparar-piloto", "--confirmar"]) == 0
    assert "Já existiam" in capsys.readouterr().out
    with sessao() as s:
        assert s.scalar(select(func.count()).select_from(Usuario)) == len(logins)


def test_preparar_piloto_em_producao_com_o_segundo_aviso(p, monkeypatch):
    from osapp import config

    monkeypatch.setenv("OS_AMBIENTE", "producao")
    monkeypatch.setattr(
        builtins, "input", lambda _p="": config.nome_do_banco(config.carregar_config().database_url)
    )
    assert cli.main(["preparar-piloto", "--confirmar", "--sei-que-e-producao"]) == 0


# --- Barra inferior -----------------------------------------------------------------------


def test_barra_inferior_altura_e_itens():
    assert 56 <= altura(True) <= 64 and altura(False) == theme.ALTURA_BARRA_CELULAR
    barra = BarraInferior(
        [("Nova OS", "a", "b"), ("Ordens", "c", "d"), ("Perfil", "e", "f")],
        1,
        lambda _i: None,
        largo=True,
        selos={1: "3"},
    )
    assert barra.controle.content.max_width == theme.LARGURA_MAX_CONTEUDO
    itens_ = barra.linha.controls
    assert len(itens_) == 3
    for item in itens_:
        assert item.height >= theme.ALVO_TOQUE_MIN and item.tooltip
    icone_ordens = itens_[1].content.controls[0].content
    assert icone_ordens.semantics_label == "Ordens" and icone_ordens.badge.label == "3"
    rotulo_sel = itens_[1].content.controls[1]
    assert rotulo_sel.weight is not None  # selecionado: negrito (não só a cor)
    barra.definir_selo(1, None)
    assert barra.linha.controls[1].content.controls[0].content.badge is None
