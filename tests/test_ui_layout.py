"""Prompt 23: tema e contraste, barra inferior, seções do formulário, contadores e
componentes compartilhados."""

from __future__ import annotations

import pytest

from osapp.db import sessao
from osapp.models import Usuario
from osapp.services import ordens
from osapp.services.erros import ErroPermissao
from osapp.ui import navegacao, rotas, secoes, theme, urgencia
from osapp.ui.components.chips import GrupoChips
from osapp.ui.components.opcoes import ETIQUETA_SELECIONADO, OpcaoGrupo
from osapp.ui.components.secao import titulo_secao
from osapp.ui.views.perfil import itens_do_perfil
from tests.fabricas import nova_os, novo_usuario

# --- Contraste -------------------------------------------------------------------------


def test_contraste_de_pares_conhecidos():
    assert theme.contraste("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert theme.contraste("#FFFFFF", "#FFFFFF") == pytest.approx(1.0)
    assert theme.contraste("#FFFFFF", "#000000") == theme.contraste("#000000", "#FFFFFF")
    # O cinza antigo do texto secundário reprovava sobre o fundo da página.
    assert theme.contraste("#6B7280", theme.COR_FUNDO_PAGINA) < theme.CONTRASTE_MIN


@pytest.mark.parametrize("nome", sorted(theme.PARES_TEXTO))
def test_todo_par_texto_fundo_do_tema_passa_no_aa(nome):
    texto, fundo = theme.PARES_TEXTO[nome]
    assert theme.contraste(texto, fundo) >= theme.CONTRASTE_MIN, nome


def test_laranja_nunca_e_cor_de_texto_declarada():
    assert all(texto != theme.COR_DESTAQUE for texto, _ in theme.PARES_TEXTO.values())


def test_cores_de_urgencia_cobrem_todos_os_niveis():
    assert set(theme.COR_PONTO_URGENCIA) == set(ordens.NIVEIS)
    assert theme.cor_ponto_urgencia(None) == theme.COR_PONTO_NEUTRO


# --- Navegação ------------------------------------------------------------------------


def test_nova_os_abre_a_tela_certa_por_papel():
    assert navegacao.nova_os("usuario").rota == rotas.SOLICITACAO_NOVA
    assert navegacao.nova_os("manutencao").rota == rotas.OS_NOVA
    assert navegacao.nova_os("admin").rota == rotas.OS_NOVA


def test_destino_ativo_marca_o_pai_das_subtelas():
    papel = "manutencao"
    nomes = [d.chave for d in navegacao.destinos(papel)]

    def ativo(rota):
        indice = navegacao.destino_ativo(papel, rota)
        return None if indice is None else nomes[indice]

    assert ativo("/") == "ordens" and ativo("/os/7") == "ordens"
    assert ativo("/os/7/concluir") == "ordens"
    assert ativo("/os/nova") == "nova_os"
    assert ativo("/relatorios/mensal") == "relatorios"
    assert ativo("/configuracoes") == "perfil" and ativo("/usuarios/3") == "perfil"
    assert ativo("/perfil/senha") == "perfil"


def test_rotas_do_perfil():
    assert rotas.resolver("/perfil") == ("perfil", {})
    assert rotas.resolver("/perfil/senha") == ("alterar_senha", {})
    assert rotas.rota_anterior("/perfil/senha") == rotas.PERFIL
    assert rotas.rota_anterior("/usuarios") == rotas.PERFIL


def test_itens_do_perfil_por_papel():
    assert itens_do_perfil("usuario") == ("configuracoes", "alterar_senha", "sair")
    assert itens_do_perfil("manutencao") == ("configuracoes", "alterar_senha", "sair")
    assert itens_do_perfil("admin") == (
        "configuracoes",
        "alterar_senha",
        "usuarios",
        "nova_solicitacao",
        "sair",
    )


# --- Seções do formulário -----------------------------------------------------------

S, U, P, IT, C = (
    secoes.SOLICITACAO,
    secoes.URGENCIA,
    secoes.PLANEJAMENTO,
    secoes.ITENS,
    secoes.CONCLUSAO,
)


@pytest.mark.parametrize(
    ("papel", "status", "solicitacao", "pode_concluir", "esperado"),
    [
        # Nova Solicitação (qualquer papel): 1 e 2; manutenção vê também 3 e 4.
        ("usuario", None, True, False, (S, U)),
        ("manutencao", None, True, False, (S, U, P, IT)),
        # Nova Ordem de Serviço (manutenção): sem urgência, que o serviço não aceita.
        ("manutencao", None, False, False, (S, P, IT)),
        ("admin", None, False, False, (S, P, IT)),
        # Aberta e em execução.
        ("usuario", "ABERTA", True, False, (S, U)),
        ("manutencao", "ABERTA", True, False, (S, U, P, IT)),
        ("manutencao", "EM_EXECUCAO", True, False, (S, U, P, IT)),
        ("manutencao", "EM_EXECUCAO", True, True, (S, U, P, IT, C)),
        ("admin", "EM_EXECUCAO", False, True, (S, P, IT, C)),
        # O usuario nunca recebe a seção de conclusão em execução, mesmo se pedisse.
        ("usuario", "EM_EXECUCAO", True, True, (S, U)),
        # Concluída: conclusão só leitura para todos (para o usuario, só a nota).
        ("usuario", "CONCLUIDA", True, False, (S, U, C)),
        ("manutencao", "CONCLUIDA", True, False, (S, U, P, IT, C)),
        ("manutencao", "CANCELADA", True, False, (S, U, P, IT)),
    ],
)
def test_secoes_por_papel_e_status(papel, status, solicitacao, pode_concluir, esperado):
    assert secoes.secoes(papel, status, solicitacao, pode_concluir) == esperado


def test_numeros_das_secoes_e_titulo():
    lista = secoes.secoes("manutencao", "EM_EXECUCAO", True, True)
    assert [secoes.numero(lista, c) for c in lista] == [1, 2, 3, 4, 5]
    assert titulo_secao(1, "Solicitação", obrigatoria=True) == "1. SOLICITAÇÃO *"
    assert titulo_secao(3, "Itens de custo") == "3. ITENS DE CUSTO"
    assert titulo_secao(None, "Histórico") == "HISTÓRICO"


# --- Urgência e componentes ---------------------------------------------------------


def test_textos_da_urgencia():
    assert urgencia.SIGNIFICADO == {
        "baixa": "Pode aguardar, nada parado",
        "media": "Atrapalha, mas há alternativa",
        "alta": "Prejudica a produção",
        "emergencial": "Equipamento parado ou risco de segurança",
    }
    assert urgencia.pill("alta") == "URGÊNCIA: ALTA"
    assert [o[0] for o in urgencia.opcoes(theme.COR_PONTO_URGENCIA)] == list(ordens.NIVEIS)


def _textos(controle, so_visiveis=False):
    import flet as ft

    achados = []
    if so_visiveis and not controle.visible:
        return achados
    if isinstance(controle, ft.Text):
        achados.append(controle.value)
    for filho in getattr(controle, "controls", None) or []:
        achados += _textos(filho, so_visiveis)
    conteudo = getattr(controle, "content", None)
    if isinstance(conteudo, ft.Control):
        achados += _textos(conteudo, so_visiveis)
    return achados


def test_opcao_grupo_aceita_exatamente_uma_escolha():
    grupo = OpcaoGrupo(urgencia.opcoes(theme.COR_PONTO_URGENCIA))
    assert grupo.valor is None
    assert ETIQUETA_SELECIONADO not in _textos(grupo.controle, so_visiveis=True)
    grupo.escolher("alta")
    grupo.escolher("baixa")
    assert grupo.valor == "baixa"
    textos = _textos(grupo.controle)
    assert _textos(grupo.controle, so_visiveis=True).count(ETIQUETA_SELECIONADO) == 1
    # O significado aparece no cartão (não só a cor).
    assert "Pode aguardar, nada parado" in textos


def test_grupo_de_chips_unico_e_multiplo():
    unico = GrupoChips([("a", "A"), ("b", "B")], "a", opcional=False)
    unico.alternar("a")
    assert unico.valor == "a"  # não desmarca quando a escolha é obrigatória
    unico.alternar("b")
    assert unico.valor == "b"
    opcional = GrupoChips([("a", "A")], "a")
    opcional.alternar("a")
    assert opcional.valor is None
    multiplo = GrupoChips([(1, "Um"), (2, "Dois")], {1, 2}, multipla=True, minimo=1)
    multiplo.alternar(1)
    multiplo.alternar(2)  # o último fica marcado
    assert multiplo.valor == {2}


# --- Contadores (services.ordens.contadores) -----------------------------------------


@pytest.fixture
def ordens_fixas(cenario):
    """F001: 3 ABERTA, 2 EM_EXECUCAO, 1 CONCLUIDA, 1 CANCELADA. F002: 1 ABERTA, 1 EM_EXECUCAO."""
    with sessao() as s:
        f1 = s.get(Usuario, cenario["marina"]).filial
        f2 = s.get(Usuario, cenario["carlos"]).filial
        criador1 = s.get(Usuario, cenario["marina"])
        criador2 = s.get(Usuario, cenario["carlos"])
        situacoes = [
            (f1, criador1, "ABERTA"),
            (f1, criador1, "ABERTA"),
            (f1, criador1, "ABERTA"),
            (f1, criador1, "EM_EXECUCAO"),
            (f1, criador1, "EM_EXECUCAO"),
            (f1, criador1, "CONCLUIDA"),
            (f1, criador1, "CANCELADA"),
            (f2, criador2, "ABERTA"),
            (f2, criador2, "EM_EXECUCAO"),
        ]
        for n, (filial, criador, status) in enumerate(situacoes, start=1):
            nova_os(s, filial, criador, f"OS-2026-{n:06d}", status=status)
        cenario["solicitante"] = novo_usuario(s, f1, "sol.norte", "Sara", papel="usuario").id
    return cenario


def test_contadores_com_dados_fixos(ordens_fixas):
    c = ordens.contadores(ordens_fixas["marina"])
    assert (c.abertas, c.aguardando_inicio) == (5, 3)
    assert c.filial_rotulo == "F001 - Filial Modelo Norte"


def test_contadores_escopo_da_filial(ordens_fixas):
    todas = ordens.contadores(ordens_fixas["admin"])
    assert (todas.abertas, todas.aguardando_inicio, todas.filial_rotulo) == (
        7,
        4,
        "Todas as filiais",
    )
    so_f2 = ordens.contadores(ordens_fixas["admin"], ordens_fixas["f2"])
    assert (so_f2.abertas, so_f2.aguardando_inicio) == (2, 1)
    assert ordens.contadores(ordens_fixas["carlos"]).abertas == 2
    with pytest.raises(ErroPermissao):
        ordens.contadores(ordens_fixas["marina"], ordens_fixas["f2"])


def test_usuario_recebe_so_a_propria_filial(ordens_fixas):
    c = ordens.contadores(ordens_fixas["solicitante"])
    assert (c.abertas, c.aguardando_inicio) == (5, 3)
    assert ordens.contadores(ordens_fixas["solicitante"], ordens_fixas["f1"]).abertas == 5
    with pytest.raises(ErroPermissao):
        ordens.contadores(ordens_fixas["solicitante"], ordens_fixas["f2"])
