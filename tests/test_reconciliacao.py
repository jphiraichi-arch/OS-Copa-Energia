"""Prompt 29: uma verificação por regra corrigida dos prompts 10 a 19 (A1 a D19).

Regras já cobertas por testes anteriores apontam para eles na tabela da resposta; aqui
ficam as que ainda não tinham um teste próprio.
"""

from __future__ import annotations

import inspect
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from osapp import cli
from osapp.db import Base, sessao
from osapp.models import Usuario
from osapp.services import custos, ordens, relatorios, relogio
from osapp.services import status as st
from osapp.services.erros import ErroNaoEncontrado, ErroPermissao, ErroValidacao
from osapp.ui import navegacao, rotas, secoes
from tests.conftest import RAIZ
from tests.fabricas import categoria_id, novo_usuario, tipo_id

T0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
UI = RAIZ / "src" / "osapp" / "ui"


def _texto(caminho) -> str:
    return caminho.read_text(encoding="utf-8")


@pytest.fixture
def c(cenario, monkeypatch):
    """O cenário padrão (marina, joao, pedro: manutenção da F001; carlos: F002; admin;
    inativa) mais dois usuarios da F001: o solicitante e outro."""
    monkeypatch.setattr(relogio, "agora", lambda: T0)
    with sessao() as s:
        filial = s.get(Usuario, cenario["marina"]).filial
        cenario["sol"] = novo_usuario(s, filial, "sol.um", "Sol Um", papel="usuario").id
        cenario["outro_sol"] = novo_usuario(s, filial, "sol.dois", "Sol Dois", papel="usuario").id
    return cenario


def _item(valor=1000):
    return custos.ItemEntrada(categoria_id(), "Peça", Decimal("1"), valor)


def _solicitacao_completa(c):
    v = ordens.criar_solicitacao(c["sol"], "Pedido da área", "Descrição do pedido.", "alta")
    d = ordens.obter_os(c["marina"], v.id)
    d = ordens.editar_os(
        c["marina"],
        d.id,
        d.versao,
        {"tempo_previsto_minutos": 60, "tipo_id": tipo_id(), "prioridade": "media"},
    )
    return custos.adicionar_item(
        c["marina"], d.id, d.versao, "PREVISTO", categoria_id(), "Peça", Decimal("1"), 500
    )


def _no_status(c, destino):
    d = _solicitacao_completa(c)
    if destino == st.CANCELADA:
        return ordens.cancelar(c["admin"], d.id, d.versao)
    if destino in (st.EM_EXECUCAO, st.CONCLUIDA):
        d = ordens.iniciar_execucao(c["pedro"], d.id, d.versao)
    if destino == st.CONCLUIDA:
        d = ordens.concluir_os(
            c["pedro"],
            d.id,
            d.versao,
            [_item(700)],
            T0 - timedelta(hours=3),
            T0 - timedelta(hours=1),
            "Feito.",
            "Pronto, obrigado.",
        )
    return d


# --- A. Relatórios e navegação -----------------------------------------------------------


def test_regra_01_relatorios_so_pela_barra_inferior():
    for papel in ("manutencao", "admin"):
        assert rotas.RELATORIOS in [d.rota for d in navegacao.destinos(papel)]
    app = _texto(UI / "app.py") + _texto(UI / "components" / "cabecalho.py")
    assert "PopupMenuButton" not in app and "NavigationRail" not in app


def test_regra_02_so_o_app_monta_a_navegacao_e_usa_a_funcao_pura():
    arquivos = [p for p in UI.rglob("*.py") if "__pycache__" not in p.parts]
    com_barra = sorted(
        p.relative_to(UI).as_posix()
        for p in arquivos
        if re.search(r"ft\.(NavigationBar|NavigationRail)\(", _texto(p))
    )
    assert com_barra == ["app.py"]
    assert "navegacao.destinos(" in _texto(UI / "app.py")
    assert "import flet" not in _texto(UI / "navegacao.py")  # função pura


def test_regra_03_usuario_sem_relatorios(c):
    assert rotas.RELATORIOS not in [d.rota for d in navegacao.destinos("usuario")]
    assert not navegacao.ve_relatorios("usuario")
    for chamada in (
        lambda: relatorios.relatorio_tempos(c["sol"]),
        lambda: relatorios.relatorio_mensal(c["sol"], 2026, 5),
        lambda: relatorios.gerar_relatorio(c["sol"], 2026, 5),
    ):
        with pytest.raises(ErroPermissao):
            chamada()


# --- B. Papéis ---------------------------------------------------------------------------


def test_regra_04_papel_e_a_unica_fonte_do_papel():
    assert "is_" + "admin" not in Usuario.__table__.c
    assert "papel" in Usuario.__table__.c
    # Os três nomes antigos das propriedades de papel (hoje e_admin, e_usuario,
    # e_manutencao), montados por partes para este arquivo não se acusar.
    proibido = re.compile(r"\bis_(" + "admin|usuario|manutencao" + r")\b")
    achados = []
    for pasta in ("src", "tests"):
        for p in (RAIZ / pasta).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            for n, linha in enumerate(_texto(p).splitlines(), 1):
                # Testes de migração escrevem na coluna do esquema antigo (antes da 0008).
                if proibido.search(linha) and "esquema antigo" not in linha:
                    achados.append(f"{p.relative_to(RAIZ)}:{n}")
    assert achados == []


# --- C. Itens de custo -----------------------------------------------------------------


def test_regra_08_usuario_nunca_recebe_itens_nem_totais(c):
    d = _no_status(c, st.CONCLUIDA)
    sensivel = re.compile(r"iten|custo|previsto|realizado|total|centavos|valor", re.I)
    for modelo in (ordens.OsVisaoSolicitante, ordens.ResumoSolicitante):
        assert not [f for f in modelo.__dataclass_fields__ if sensivel.search(f)]
    v = ordens.obter_os(c["sol"], d.id)
    assert isinstance(v, ordens.OsVisaoSolicitante)
    assert all(isinstance(i, ordens.ResumoSolicitante) for i in ordens.listar_os(c["sol"]).itens)
    # Busca: o usuario nunca busca nos itens ('peca' só existe num item).
    for escopo in ordens.ESCOPOS:
        assert ordens.listar_os(c["sol"], "peca", None, None, 1, None, escopo).itens == ()
    with pytest.raises(ErroPermissao):
        custos.sugerir_descricoes(c["sol"], v and ordens.obter_os(c["admin"], d.id).filial_id, "pe")
    with pytest.raises(ErroPermissao):
        ordens.listar_eventos(c["sol"], d.id)


def test_regra_09_criar_os_aceita_lista_vazia_e_solicitacao_nao_tem_itens(c):
    d = ordens.criar_os(c["marina"], "Ordem sem itens", "Descrição.", [])
    assert d.itens == () and d.origem == ordens.ORIGEM_MANUTENCAO
    assert "iten" not in " ".join(inspect.signature(ordens.criar_solicitacao).parameters)
    with pytest.raises(ErroPermissao):
        ordens.criar_os(c["sol"], "Usuario não cria", "Descrição.", [])


def test_regra_10_previsto_completo_e_a_unica_verificacao(c):
    d = ordens.criar_os(c["marina"], "Ordem vazia", "Descrição.", [])
    assert set(d.pendencias_para_iniciar) == {
        ordens.PENDENCIA_TEMPO,
        ordens.PENDENCIA_VALOR,
        ordens.PENDENCIA_TIPO,
        ordens.PENDENCIA_PRIORIDADE,
    }
    assert not re.search("equip" + "ament", " ".join(d.pendencias_para_iniciar), re.I)
    fonte = inspect.getsource(ordens.iniciar_execucao)
    assert "pendencias_para_iniciar(" in fonte  # a mesma função, não uma cópia
    assert inspect.getsource(ordens.previsto_completo).count("pendencias_para_iniciar") == 1


def test_regra_11_concluir_exige_itens_realizados_e_nota(c):
    d = _no_status(c, st.EM_EXECUCAO)
    args = (T0 - timedelta(hours=3), T0 - timedelta(hours=1), "Feito.")
    with pytest.raises(ErroValidacao) as sem_itens:
        ordens.concluir_os(c["pedro"], d.id, d.versao, [], *args, "Pronto, obrigado.")
    assert sem_itens.value.campo == "itens_realizados"
    with pytest.raises(ErroValidacao) as sem_nota:
        ordens.concluir_os(c["pedro"], d.id, d.versao, [_item()], *args, "")
    assert sem_nota.value.campo == "nota_conclusao"


def test_regra_12_nenhum_bem_cadastrado(capsys):
    proibido = re.compile("equip" + "ament", re.I)
    assert not [t for t in Base.metadata.tables if proibido.search(t)]
    for tabela in Base.metadata.tables.values():
        assert not [col.name for col in tabela.c if proibido.search(col.name)]
    from osapp import services

    for modulo in vars(services).values():
        if inspect.ismodule(modulo):
            assert not [n for n in vars(modulo) if proibido.search(n)]
    comandos = cli.criar_parser()._subparsers._group_actions[0].choices
    assert not [n for n in comandos if proibido.search(n)]


ATORES14 = ["sol", "outro_sol", "marina", "pedro", "carlos", "admin", "inativa"]
#           solicitante, outro usuario, manutenção da filial, executor, outra filial,
#           administrador, inativa


def _esperado14(ator, fase, status_os):
    from osapp.services.erros import ErroAutenticacao

    if ator == "inativa":
        return ErroAutenticacao
    if ator == "carlos":
        return ErroNaoEncontrado  # outra filial: a ordem nem é visível
    if ator in ("sol", "outro_sol"):
        return ErroPermissao
    if status_os == st.CANCELADA:
        return ErroPermissao  # ninguém mexe numa cancelada
    if fase == "PREVISTO":
        if ator == "admin":
            return "ok"
        return "ok" if status_os != st.CONCLUIDA else ErroPermissao
    return "ok" if (ator == "admin" and status_os == st.CONCLUIDA) else ErroPermissao


CELULAS14 = [
    (ator, fase, s)
    for s in (st.ABERTA, st.EM_EXECUCAO, st.CONCLUIDA, st.CANCELADA)
    for fase in ("PREVISTO", "REALIZADO")
    for ator in ATORES14
]


@pytest.mark.parametrize(("ator", "fase", "status_os"), CELULAS14)
def test_regra_14_matriz_de_itens_com_usuario_e_cancelada(c, ator, fase, status_os):
    """Completa a matriz de test_custos (que não tinha usuario nem cancelada)."""
    d = _no_status(c, status_os)
    esperado = _esperado14(ator, fase, status_os)

    def adicionar():
        return custos.adicionar_item(
            c[ator], d.id, d.versao, fase, categoria_id(), "Novo", Decimal("1"), 10
        )

    if esperado == "ok":
        assert adicionar().versao == d.versao + 1
    else:
        with pytest.raises(esperado):
            adicionar()


# --- D. Telas -----------------------------------------------------------------------------


def test_regra_15_nova_os_so_manutencao_e_admin_solicitacao_sem_custos():
    assert navegacao.nova_os("usuario").rota == rotas.SOLICITACAO_NOVA
    assert {navegacao.nova_os(p).rota for p in ("manutencao", "admin")} == {rotas.OS_NOVA}
    fonte = _texto(UI / "views" / "solicitacao.py")
    assert "EditorItens" not in fonte and "custos" not in fonte
    assert secoes.ITENS not in secoes.secoes("usuario", None, solicitacao=True)


def test_regra_16_na_criacao_tempo_e_itens_sao_opcionais(c):
    d = ordens.criar_os(c["marina"], "Só o título", "Descrição.")
    assert (d.tempo_previsto_minutos, d.itens) == (None, ())


def test_regra_17_assumir_usa_tempo_e_itens_e_lista_o_que_falta(c):
    from osapp.ui.views import os_formulario

    fonte = inspect.getsource(os_formulario.EditarOs) + inspect.getsource(os_formulario.AssumirOs)
    assert "EditorItens(" in fonte and "pendencias" in fonte
    assert "CampoDuracao" in _texto(UI / "components" / "formulario_os.py")
    assert "valor_previsto_centavos" not in _texto(UI / "views" / "os_formulario.py")
    v = ordens.criar_solicitacao(c["sol"], "Sem previsto", "Descrição.", "alta")
    d = ordens.obter_os(c["marina"], v.id)
    with pytest.raises(ErroValidacao) as faltas:
        ordens.iniciar_execucao(c["marina"], d.id, d.versao)
    for pendencia in (ordens.PENDENCIA_TEMPO, ordens.PENDENCIA_VALOR, ordens.PENDENCIA_TIPO):
        assert pendencia in faltas.value.mensagem


def test_regra_18_concluir_mantem_a_nota_obrigatoria():
    fonte = _texto(UI / "views" / "concluir.py")
    assert '"Nota para o solicitante"' in fonte and '"nota_conclusao": self.nota' in fonte


def test_regra_19_telas_do_usuario_nao_pedem_custos():
    from osapp.ui.views import detalhe

    solicitante = inspect.getsource(detalhe.Detalhe._montar_solicitante)
    assert not re.search(r"resumo_custos|\.itens\b|_custos\(|listar_eventos", solicitante)
    carregar = inspect.getsource(detalhe.Detalhe.carregar)
    assert "not solicitante" in carregar  # o histórico não é pedido para o usuario
    home = _texto(UI / "views" / "home.py")
    assert "ResumoSolicitante" in home  # o cartão do usuario usa o modelo reduzido
