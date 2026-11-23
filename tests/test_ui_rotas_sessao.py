from datetime import UTC, datetime, timedelta

import pytest

from osapp.services.auth import Ator
from osapp.ui import rotas
from osapp.ui.sessao import (
    MENSAGEM_SESSAO_EXPIRADA,
    SessaoUI,
    aplicar_navegacao,
    autenticada,
    decidir_rota,
    encerrar,
    expirada,
    iniciar,
    registrar_atividade,
)

T0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
ATOR = Ator(
    usuario_id=7, nome="Marina Teste", filial_id=1, filial_codigo="F001", papel="manutencao"
)
TODAS = ["/login", "/", "/os/nova", "/os/12", "/os/12/editar", "/os/12/concluir"]


def deslogada() -> SessaoUI:
    return SessaoUI(timeout_min=30)


def logada(ultima=T0) -> SessaoUI:
    s = SessaoUI(timeout_min=30)
    iniciar(s, ATOR, ultima)
    return s


# --- tabela de rotas ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rota", "esperado"),
    [
        ("/login", ("login", {})),
        ("/", ("home", {})),
        ("", ("home", {})),
        (None, ("home", {})),
        ("/os/nova", ("os_nova", {})),
        ("/os/12", ("os_detalhe", {"os_id": 12})),
        ("/os/12/", ("os_detalhe", {"os_id": 12})),
        ("/os/12?x=1", ("os_detalhe", {"os_id": 12})),
        ("/os/12/editar", ("os_editar", {"os_id": 12})),
        ("/os/12/concluir", ("os_concluir", {"os_id": 12})),
    ],
)
def test_resolver_rotas_conhecidas(rota, esperado):
    assert rotas.resolver(rota) == esperado


@pytest.mark.parametrize(
    "rota",
    [
        "/admin",
        "/os",
        "/os/",
        "/os/abc",
        "/os/0",
        "/os/-1",
        "/os/1/apagar",
        "/os/1/editar/x",
        "/os/1e3",
        "/login/x",
        "/os/12345678901234567890",
    ],
)
def test_rota_desconhecida_vai_para_a_home(rota):
    assert rotas.resolver(rota) is None
    assert rotas.normalizar(rota) == "/"


def test_rota_anterior_e_construtores():
    assert rotas.rota_anterior("/") is None and rotas.rota_anterior("/login") is None
    assert rotas.rota_anterior("/os/nova") == "/"
    assert rotas.rota_anterior("/os/5") == "/"
    assert rotas.rota_anterior("/os/5/editar") == "/os/5"
    assert rotas.rota_anterior("/os/5/concluir") == "/os/5"
    assert (rotas.rota_os(5), rotas.rota_editar(5), rotas.rota_concluir(5)) == (
        "/os/5",
        "/os/5/editar",
        "/os/5/concluir",
    )


# --- decidir_rota ---------------------------------------------------------------------


@pytest.mark.parametrize("rota", TODAS + ["/desconhecida", "", None])
def test_sem_login_toda_rota_vai_para_login(rota):
    assert decidir_rota(rota, deslogada(), T0) == "/login"


@pytest.mark.parametrize("rota", [r for r in TODAS if r != "/login"])
def test_com_login_a_rota_pedida_e_mostrada(rota):
    assert decidir_rota(rota, logada(), T0 + timedelta(minutes=5)) == rota


def test_com_login_em_login_vai_para_a_home():
    assert decidir_rota("/login", logada(), T0) == "/"


def test_com_login_rota_desconhecida_vai_para_a_home():
    assert decidir_rota("/nao-existe", logada(), T0) == "/"
    assert decidir_rota("/os/abc", logada(), T0) == "/"


@pytest.mark.parametrize("rota", TODAS)
def test_sessao_expirada_vai_para_login(rota):
    assert decidir_rota(rota, logada(), T0 + timedelta(minutes=30)) == "/login"


def test_decidir_rota_e_pura():
    s = logada()
    antes = SessaoUI(**vars(s))
    decidir_rota("/os/1", s, T0 + timedelta(hours=5))
    assert s == antes


def test_link_direto_e_lembrado_ate_o_login():
    s = deslogada()
    assert aplicar_navegacao("/os/12/editar", s, T0) == "/login"
    assert s.rota_pendente == "/os/12/editar"
    assert aplicar_navegacao("/login", s, T0) == "/login"  # o redirecionamento não apaga
    assert s.rota_pendente == "/os/12/editar"
    pendente = s.rota_pendente
    iniciar(s, ATOR, T0)
    assert decidir_rota("/login", s, T0) == pendente == "/os/12/editar"
    assert aplicar_navegacao(pendente, s, T0) == "/os/12/editar"
    assert s.rota_pendente is None  # usada uma vez


def test_rota_desconhecida_nao_e_lembrada():
    s = deslogada()
    aplicar_navegacao("/nao-existe", s, T0)
    assert s.rota_pendente is None


# --- tempo de inatividade -------------------------------------------------------------


@pytest.mark.parametrize(
    ("minutos", "esperado"), [(0, False), (29, False), (29.99, False), (30, True), (500, True)]
)
def test_aritmetica_do_tempo_limite(minutos, esperado):
    s = logada()
    agora = T0 + timedelta(minutes=minutos)
    assert expirada(s, agora) is esperado
    assert autenticada(s, agora) is (not esperado)


def test_sessao_sem_login_nunca_esta_expirada():
    assert expirada(deslogada(), T0 + timedelta(days=1)) is False
    assert autenticada(deslogada(), T0) is False


def test_atividade_renova_o_prazo():
    s = logada()
    assert aplicar_navegacao("/", s, T0 + timedelta(minutes=20)) == "/"  # navegar é atividade
    assert s.ultima_atividade == T0 + timedelta(minutes=20)
    registrar_atividade(s, T0 + timedelta(minutes=45))  # chamada de serviço
    assert aplicar_navegacao("/os/nova", s, T0 + timedelta(minutes=70)) == "/os/nova"


def test_expiracao_encerra_a_sessao_e_deixa_a_mensagem():
    s = logada()
    assert aplicar_navegacao("/os/3", s, T0 + timedelta(minutes=31)) == "/login"
    assert s.ator_id is None and s.nome == "" and s.filial_codigo == "" and not s.e_admin
    assert s.mensagem_login == MENSAGEM_SESSAO_EXPIRADA == "Sessão expirada. Entre novamente."
    assert s.rota_pendente == "/os/3"


def test_tempo_limite_configuravel():
    s = SessaoUI(timeout_min=5)
    iniciar(s, ATOR, T0)
    assert not expirada(s, T0 + timedelta(minutes=4))
    assert expirada(s, T0 + timedelta(minutes=5))


def test_iniciar_e_encerrar():
    s = logada()
    assert (s.ator_id, s.nome, s.filial_id, s.filial_codigo, s.e_admin) == (
        7,
        "Marina Teste",
        1,
        "F001",
        False,
    )
    encerrar(s)
    assert s.ator_id is None and s.mensagem_login is None
    registrar_atividade(s, T0)
    assert s.ultima_atividade is None  # sem login não há atividade


def test_sessao_nao_guarda_senha_nem_hash():
    campos = set(vars(logada()))
    assert not {c for c in campos if "senha" in c or "hash" in c or "token" in c}


# --- camadas --------------------------------------------------------------------------


def test_ui_nao_importa_modelos_nem_repositorios():
    import re
    from pathlib import Path

    raiz = Path(__file__).resolve().parents[1] / "src" / "osapp"
    proibido = re.compile(r"^\s*(from|import)\s+osapp\.(models|repositories|db)\b", re.M)
    infratores = [
        str(a.relative_to(raiz))
        for a in [*sorted((raiz / "ui").rglob("*.py")), raiz / "main.py"]
        if proibido.search(a.read_text(encoding="utf-8"))
    ]
    assert not infratores
