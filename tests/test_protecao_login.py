"""Atraso progressivo do login (por login e por IP), chaves HMAC e IP atrás de proxy."""

import asyncio
import logging
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from starlette.websockets import WebSocket
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from osapp import cli
from osapp.config import ConfigError
from osapp.db import sessao
from osapp.models import TentativaLogin
from osapp.services import administracao, protecao_login, relogio, senhas
from osapp.services.auth import autenticar
from osapp.services.erros import ErroAutenticacao, ErroMuitasTentativas
from osapp.services.protecao_login import ATRASO_MAXIMO, TIPO_IP, TIPO_LOGIN, atraso

SENHA = "senha-ficticia-123"
T0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
IP_A = "203.0.113.10"
IP_B = "198.51.100.20"
RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture
def usuarios(banco):
    administracao.criar_filial("F001", "Filial Modelo Norte")
    administracao.criar_usuario("Marina Teste", "marina.teste", SENHA, "F001")
    administracao.criar_usuario("Administrador Fictício", "admin", SENHA, "F001", True)


class Relogio:
    """Relógio substituto: os testes avançam o tempo em vez de dormir."""

    def __init__(self, monkeypatch) -> None:
        self.agora = T0
        monkeypatch.setattr(relogio, "agora", lambda: self.agora)

    def avancar(self, **kw) -> None:
        self.agora += timedelta(**kw)


@pytest.fixture
def tempo(monkeypatch):
    return Relogio(monkeypatch)


def tentar(login, senha="senha-errada", ip=IP_A):
    """Tipo do erro (ou 'ok')."""
    try:
        autenticar(login, senha, ip)
    except ErroMuitasTentativas:
        return "espera"
    except ErroAutenticacao:
        return "falha"
    return "ok"


def linha(tipo, valor):
    chave = (
        protecao_login.chave_do_login(valor)
        if tipo == TIPO_LOGIN
        else (protecao_login.chave_do_ip(valor))
    )
    with sessao() as s:
        t = s.query(TentativaLogin).filter_by(tipo=tipo, chave=chave).one_or_none()
        return None if t is None else (t.falhas, t.proximo_permitido_em)


# --- Regra pura -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("falhas", "segundos"),
    [(1, 0), (2, 0), (3, 0), (4, 2), (5, 4), (6, 8), (7, 16), (12, 512), (13, 900), (40, 900)],
)
def test_atraso_por_login(falhas, segundos):
    assert atraso(falhas, protecao_login.FALHAS_LIVRES_LOGIN) == timedelta(seconds=segundos)


def test_atraso_por_ip_e_teto():
    assert atraso(20, protecao_login.FALHAS_LIVRES_IP) == timedelta(0)
    assert atraso(21, protecao_login.FALHAS_LIVRES_IP) == timedelta(seconds=2)
    assert atraso(10**6, 3) == ATRASO_MAXIMO == timedelta(minutes=15)


# --- Por login --------------------------------------------------------------------------


def test_tres_falhas_livres_depois_2_4_8_segundos(usuarios, tempo):
    for _ in range(3):
        assert tentar("marina.teste") == "falha"
        assert linha(TIPO_LOGIN, "marina.teste")[1] is None
    assert tentar("marina.teste") == "falha"  # 4ª falha
    assert linha(TIPO_LOGIN, "marina.teste") == (4, T0 + timedelta(seconds=2))
    # Antes do instante permitido: recusada, mesmo com a senha certa, sem contar falha.
    tempo.avancar(seconds=1)
    assert tentar("marina.teste", SENHA) == "espera"
    assert linha(TIPO_LOGIN, "marina.teste")[0] == 4
    tempo.avancar(seconds=1)
    assert tentar("marina.teste") == "falha"  # 5ª falha: espera de 4 s
    assert linha(TIPO_LOGIN, "marina.teste") == (5, tempo.agora + timedelta(seconds=4))
    tempo.avancar(seconds=4)
    assert tentar("marina.teste") == "falha"  # 6ª: 8 s
    assert linha(TIPO_LOGIN, "marina.teste") == (6, tempo.agora + timedelta(seconds=8))


def test_teto_de_15_minutos(usuarios, tempo):
    esperas = []
    for n in range(1, 16):
        assert tentar("marina.teste", ip=f"192.0.2.{n}") == "falha"
        proximo = linha(TIPO_LOGIN, "marina.teste")[1]
        esperas.append(0 if proximo is None else int((proximo - tempo.agora).total_seconds()))
        tempo.avancar(minutes=15)
    assert esperas == [0, 0, 0, 2, 4, 8, 16, 32, 64, 128, 256, 512, 900, 900, 900]


def test_sucesso_zera_a_contagem_do_login(usuarios, tempo):
    for _ in range(5):
        tempo.avancar(seconds=10)
        assert tentar("marina.teste") == "falha"
    tempo.avancar(seconds=10)
    assert tentar("marina.teste", SENHA) == "ok"
    assert linha(TIPO_LOGIN, "marina.teste") == (0, None)
    for _ in range(3):  # de novo três falhas livres
        assert tentar("marina.teste") == "falha"
    assert linha(TIPO_LOGIN, "marina.teste")[1] is None


def test_recusa_nao_confere_a_senha(usuarios, tempo, monkeypatch):
    for _ in range(4):
        tentar("marina.teste")

    def proibido(*_a, **_k):
        raise AssertionError("não deveria conferir a senha durante a espera")

    monkeypatch.setattr(senhas, "verificar", proibido)
    assert tentar("marina.teste", SENHA) == "espera"


def test_login_conhecido_e_desconhecido_se_comportam_igual(usuarios, tempo):
    resultados = {}
    for login in ("marina.teste", "nao.existe"):
        tempo.agora = T0
        sequencia = []
        for passo in range(7):
            sequencia.append(tentar(login, ip=f"192.0.2.{passo}"))
            sequencia.append(linha(TIPO_LOGIN, login))
            tempo.avancar(seconds=3)
        resultados[login] = sequencia
    assert resultados["marina.teste"] == resultados["nao.existe"]
    assert "espera" in resultados["nao.existe"]


def test_usuario_inativo_conta_como_falha_comum(usuarios, tempo):
    administracao.desativar_usuario("marina.teste")
    assert tentar("marina.teste", SENHA) == "falha"
    assert linha(TIPO_LOGIN, "marina.teste")[0] == 1


def test_redefinir_senha_zera_a_espera(usuarios, tempo):
    for _ in range(6):
        tentar("marina.teste")
    assert tentar("marina.teste", SENHA) == "espera"
    administracao.redefinir_senha("marina.teste", "nova-senha-456")
    assert tentar("marina.teste", "nova-senha-456") == "ok"


# --- Por IP -----------------------------------------------------------------------------


def test_limite_por_ip_apos_20_falhas_em_logins_diferentes(usuarios, tempo):
    for n in range(20):
        assert tentar(f"login.{n}", ip=IP_A) == "falha"
        tempo.avancar(seconds=10)
    assert linha(TIPO_IP, IP_A) == (20, None)
    assert tentar("login.20", ip=IP_A) == "falha"  # 21ª falha do IP: 2 s
    assert linha(TIPO_IP, IP_A) == (21, tempo.agora + timedelta(seconds=2))
    # O IP está em espera para qualquer login, mesmo com a senha certa.
    assert tentar("admin", SENHA, ip=IP_A) == "espera"
    # Outro IP não é afetado.
    assert tentar("admin", SENHA, ip=IP_B) == "ok"
    tempo.avancar(seconds=2)
    assert tentar("admin", SENHA, ip=IP_A) == "ok"


def test_falhas_do_ip_contam_numa_janela_de_15_minutos(usuarios, tempo):
    for n in range(20):
        tentar(f"login.{n}", ip=IP_A)
    tempo.avancar(minutes=16)  # a última falha ficou para trás: a contagem do IP recomeça
    assert tentar("outro.login", ip=IP_A) == "falha"
    assert linha(TIPO_IP, IP_A) == (1, None)


def test_ip_desconhecido_usa_chave_fixa_e_avisa(usuarios, tempo, caplog):
    with caplog.at_level(logging.WARNING):
        assert tentar("marina.teste", ip=None) == "falha"
    avisos = [r for r in caplog.records if "IP do cliente desconhecido" in r.getMessage()]
    assert len(avisos) == 1
    assert linha(TIPO_IP, protecao_login.IP_DESCONHECIDO)[0] == 1
    assert linha(TIPO_IP, "") == linha(TIPO_IP, protecao_login.IP_DESCONHECIDO)


# --- Nada cru no banco nem nos logs -----------------------------------------------------


def test_nada_cru_no_banco_nem_nos_logs(usuarios, tempo, caplog):
    with caplog.at_level(logging.DEBUG):
        for _ in range(5):
            tentar("marina.teste", "senha-errada-xyz", ip=IP_A)
            tentar("Login.Inexistente", "senha-errada-xyz", ip=IP_B)
            tempo.avancar(minutes=1)
        tentar("marina.teste", SENHA, ip=IP_A)
    with sessao() as s:
        linhas = s.query(TentativaLogin).all()
    assert linhas
    proibidos = ["marina", "inexistente", "203.0.113", "198.51.100", "senha-errada", SENHA]
    for t in linhas:
        assert len(t.chave) == 64 and all(c in "0123456789abcdef" for c in t.chave)
        assert not any(p in t.chave.lower() for p in proibidos)
    texto_dos_logs = "\n".join(r.getMessage() for r in caplog.records).lower()
    assert "falha de autenticação" in texto_dos_logs
    for p in proibidos:
        assert p.lower() not in texto_dos_logs
    assert protecao_login.chave_do_ip(IP_A) in texto_dos_logs  # a chave HMAC aparece


def test_chave_depende_do_segredo(monkeypatch):
    a = protecao_login.chave_do_login("marina.teste")
    assert protecao_login.chave_do_login(" Marina.Teste ") == a  # login normalizado
    monkeypatch.setenv("OS_HMAC_SEGREDO", "outro-segredo-" + "y" * 32)
    assert protecao_login.chave_do_login("marina.teste") != a
    assert protecao_login.chave_do_login("x") != protecao_login.chave_do_ip("x")


@pytest.mark.parametrize("valor", ["", "curto"])
def test_segredo_ausente_ou_curto_impede_iniciar(monkeypatch, valor):
    monkeypatch.setattr(protecao_login, "load_dotenv", lambda: None)
    monkeypatch.setenv("OS_HMAC_SEGREDO", valor)
    with pytest.raises(ConfigError, match="OS_HMAC_SEGREDO"):
        protecao_login.segredo()


# --- Limpeza ----------------------------------------------------------------------------


def test_cli_apaga_contadores_com_mais_de_30_dias(usuarios, tempo, capsys):
    tentar("antigo")
    tempo.avancar(days=30, seconds=1)
    tentar("recente", ip=IP_B)
    assert cli.main(["limpar-tentativas"]) == 0
    assert "2 contador(es)" in capsys.readouterr().out  # login e IP do antigo
    assert linha(TIPO_LOGIN, "antigo") is None and linha(TIPO_LOGIN, "recente") is not None


# --- IP atrás de proxy ------------------------------------------------------------------


async def _cliente_visto(trusted, cliente, xff):
    """IP que o Flet leria (WebSocket.client.host) depois do middleware do uvicorn."""
    visto = {}

    async def app(scope, receive, send):
        visto["host"] = WebSocket(scope, receive, send).client.host

    scope = {
        "type": "websocket",
        "path": "/ws",
        "headers": [(b"x-forwarded-for", xff.encode())] if xff else [],
        "client": (cliente, 50000),
        "scheme": "ws",
    }
    await ProxyHeadersMiddleware(app, trusted_hosts=trusted)(scope, None, None)
    return visto["host"]


@pytest.mark.parametrize(
    ("confiaveis", "cliente", "xff", "esperado"),
    [
        # Cabeçalho forjado por quem não é proxy confiável: ignorado.
        ("10.0.0.0/8", "203.0.113.10", "1.2.3.4", "203.0.113.10"),
        ("127.0.0.1", "203.0.113.10", "1.2.3.4", "203.0.113.10"),
        # Vindo do proxy confiável: usado.
        ("10.0.0.0/8", "10.1.2.3", "198.51.100.20", "198.51.100.20"),
        # Cliente que forja o cabeçalho atrás do proxy: vale o último IP não confiável.
        ("10.0.0.0/8", "10.1.2.3", "1.2.3.4, 198.51.100.20", "198.51.100.20"),
        # '*' confia em qualquer um e usa o primeiro IP da lista (forjável).
        ("*", "203.0.113.10", "1.2.3.4, 198.51.100.20", "1.2.3.4"),
    ],
)
def test_cabecalho_encaminhado_so_de_proxy_confiavel(confiaveis, cliente, xff, esperado):
    assert asyncio.run(_cliente_visto(confiaveis, cliente, xff)) == esperado


def test_inicializacao_limita_o_proxy_confiavel_e_sem_log_de_acesso():
    script = (RAIZ / "docker" / "iniciar.sh").read_text(encoding="utf-8")
    assert '--forwarded-allow-ips "${OS_PROXIES_CONFIAVEIS:-127.0.0.1}"' in script
    assert "--forwarded-allow-ips '*'" not in script
    assert "--no-access-log" in script  # o log de acesso do uvicorn traria o IP cru
    resultado = subprocess.run(["sh", "-n", str(RAIZ / "docker" / "iniciar.sh")], check=False)
    assert resultado.returncode == 0


def test_falhas_simultaneas_nao_se_perdem(usuarios, tempo):
    """No PostgreSQL: 12 tentativas erradas ao mesmo tempo contam 12 falhas (FOR UPDATE).

    No SQLite é pulado pelo mesmo motivo do teste de numeração (sem trava de linha).
    """
    import threading

    with sessao() as s:
        if s.get_bind().dialect.name != "postgresql":
            pytest.skip("concorrência real só no PostgreSQL (OS_TEST_DATABASE_URL)")
    total = 12
    largada = threading.Barrier(total)
    resultados = []

    def trabalho(n):
        largada.wait(timeout=30)
        resultados.append(tentar("nao.existe", ip=f"192.0.2.{n}"))

    threads = [threading.Thread(target=trabalho, args=(n,)) for n in range(total)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    falhas, _proximo = linha(TIPO_LOGIN, "nao.existe")
    # Uma tentativa pode já encontrar a espera gravada por outra: ela é recusada sem contar.
    assert falhas == resultados.count("falha")
    assert len(resultados) == total and set(resultados) <= {"falha", "espera"}
    assert falhas >= protecao_login.FALHAS_LIVRES_LOGIN + 1
