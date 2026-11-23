import ast
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from osapp.services.auth import Ator
from osapp.ui import rotas, textos
from osapp.ui.sessao import SessaoUI, aplicar_navegacao, decidir_rota, encerrar, iniciar
from osapp.ui.views.configuracoes import rotulo_do_perfil, versao_do_app

RAIZ_UI = Path(__file__).resolve().parents[1] / "src" / "osapp" / "ui"
# Arquivos que produzem os rótulos da tela principal (Home) e da navegação.
ARQUIVOS_DA_TELA_PRINCIPAL = [
    "textos.py",
    "app.py",
    "views/home.py",
    "views/configuracoes.py",
    "views/login.py",
    "views/relatorios.py",
]
SIGLA = re.compile(r"\bOS\b")
T0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
ATOR = Ator(
    usuario_id=7, nome="Marina Teste", filial_id=1, filial_codigo="F001", papel="manutencao"
)


def textos_visiveis(caminho: Path) -> list[tuple[int, str]]:
    """Todas as strings do arquivo, menos as docstrings (que o usuário não vê)."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    docstrings = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            corpo = no.body
            if (
                corpo
                and isinstance(corpo[0], ast.Expr)
                and isinstance(corpo[0].value, ast.Constant)
            ):
                docstrings.add(id(corpo[0].value))
    return [
        (no.lineno, no.value)
        for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in docstrings
    ]


@pytest.mark.parametrize("arquivo", ARQUIVOS_DA_TELA_PRINCIPAL)
def test_tela_principal_e_navegacao_nao_usam_a_sigla(arquivo):
    # Única exceção (prompt 23): 'Nova OS', o rótulo curto da barra inferior.
    infratores = [
        f"{arquivo}:{linha}: {texto!r}"
        for linha, texto in textos_visiveis(RAIZ_UI / arquivo)
        if SIGLA.search(texto) and texto != textos.NAVEGACAO_NOVA_OS
    ]
    assert not infratores, "Rótulo com a sigla em vez de 'Ordem de Serviço':\n" + "\n".join(
        infratores
    )


def test_o_detector_da_sigla_funciona():
    assert SIGLA.search("Nova OS") and SIGLA.search("Nenhuma OS encontrada.")
    assert not SIGLA.search("Ordens de Serviço") and not SIGLA.search("NOSSA OSMOSE")
    # O número da ordem é dado gravado; o detector o acusaria, por isso não é rótulo fixo.
    assert SIGLA.search("OS-2026-000001")


def test_rotulos_por_extenso():
    assert textos.HOME_TITULO == "Ordens de Serviço"
    assert textos.HOME_VAZIA == "Nenhuma Ordem de Serviço encontrada."
    assert (textos.NAVEGACAO_ORDENS, textos.NAVEGACAO_RELATORIOS) == ("Ordens", "Relatórios")
    assert textos.NAVEGACAO_PERFIL == "Perfil"
    assert textos.LOGIN_MARCA == "Ordens de Serviço"


def test_nova_os_so_na_barra_inferior():
    """'Nova OS' é a única abreviação, e só a barra inferior (navegacao.py) a usa."""
    assert textos.NAVEGACAO_NOVA_OS == "Nova OS"
    usos = [
        p.relative_to(RAIZ_UI).as_posix()
        for p in RAIZ_UI.rglob("*.py")
        if "__pycache__" not in p.parts
        and "NAVEGACAO_NOVA_OS" in p.read_text(encoding="utf-8")
    ]
    assert sorted(usos) == ["navegacao.py", "textos.py"]


def test_a_tela_principal_usa_o_modulo_de_rotulos():
    home = (RAIZ_UI / "views" / "home.py").read_text(encoding="utf-8")
    app = (RAIZ_UI / "app.py").read_text(encoding="utf-8")
    assert "textos.HOME_TITULO" in home and "textos.HOME_VAZIA" in home
    navegacao = (RAIZ_UI / "navegacao.py").read_text(encoding="utf-8")
    perfil = (RAIZ_UI / "views" / "perfil.py").read_text(encoding="utf-8")
    assert "textos.NAVEGACAO_ORDENS" in navegacao and "textos.MENU_CONFIGURACOES" in perfil
    assert "navegacao.destinos" in app


# --- Rota /configuracoes ---------------------------------------------------------------


def test_configuracoes_esta_na_tabela_de_rotas():
    assert rotas.resolver("/configuracoes") == ("configuracoes", {})
    assert rotas.normalizar("/configuracoes/") == "/configuracoes"
    assert rotas.rota_anterior("/configuracoes") == rotas.PERFIL  # prompt 23: está em Perfil
    assert rotas.CONFIGURACOES == "/configuracoes"


def test_configuracoes_nao_abre_sem_login():
    sessao = SessaoUI(timeout_min=30)
    assert decidir_rota("/configuracoes", sessao, T0) == "/login"
    assert aplicar_navegacao("/configuracoes", sessao, T0) == "/login"
    assert sessao.rota_pendente == "/configuracoes"  # volta para lá depois do login


def test_configuracoes_abre_com_login_e_fecha_quando_a_sessao_expira():
    sessao = SessaoUI(timeout_min=30)
    iniciar(sessao, ATOR, T0, "marina.teste")
    assert decidir_rota("/configuracoes", sessao, T0 + timedelta(minutes=5)) == "/configuracoes"
    assert decidir_rota("/configuracoes", sessao, T0 + timedelta(minutes=30)) == "/login"


# --- Dados mostrados em Configurações --------------------------------------------------


def test_sessao_guarda_o_login_para_exibicao():
    sessao = SessaoUI(timeout_min=30)
    iniciar(sessao, ATOR, T0, "  Marina.Teste ")
    assert sessao.login == "marina.teste"  # como o serviço o grava
    encerrar(sessao)
    assert sessao.login == ""


def test_perfil_e_versao():
    assert rotulo_do_perfil(True) == "Administrador"
    assert rotulo_do_perfil(True, True) == "Administrador"
    assert rotulo_do_perfil(False, True) == "Gerente"
    assert rotulo_do_perfil(False) == "Usuário"
    assert re.fullmatch(r"\d+\.\d+\.\d+", versao_do_app())


# --- Rota /relatorios ------------------------------------------------------------------


def test_relatorios_na_tabela_de_rotas_e_atras_da_guarda():
    assert rotas.resolver("/relatorios") == ("relatorios", {})
    assert rotas.rota_anterior("/relatorios") == "/"  # botão voltar do cabeçalho
    deslogada = SessaoUI(timeout_min=30)
    assert decidir_rota("/relatorios", deslogada, T0) == "/login"
    logada = SessaoUI(timeout_min=30)
    iniciar(logada, ATOR, T0, "marina.teste")
    assert decidir_rota("/relatorios", logada, T0) == "/relatorios"


def test_relatorios_e_destino_de_primeiro_nivel():
    from osapp.ui import navegacao

    assert rotas.RELATORIOS in [d.rota for d in navegacao.destinos("manutencao")]
    assert rotas.RELATORIOS not in [d.rota for d in navegacao.destinos("usuario")]


def test_sessao_guarda_o_perfil_de_gerente_so_para_exibicao():
    sessao = SessaoUI(timeout_min=30)
    iniciar(sessao, Ator(3, "Gabriela Gerente", 1, "F001", "manutencao", True), T0, "gerente.norte")
    assert sessao.is_gerente is True
    encerrar(sessao)
    assert sessao.is_gerente is False


def test_nome_do_mes_e_mes_vizinho():
    from osapp.ui.views.relatorios import mes_vizinho

    assert textos.nome_do_mes(2026, 11) == "novembro de 2026"
    assert textos.nome_do_mes(2026, 3) == "março de 2026"
    assert mes_vizinho(2026, 1, -1) == (2025, 12)
    assert mes_vizinho(2026, 12, 1) == (2027, 1)
    assert mes_vizinho(2026, 5, 1) == (2026, 6)
