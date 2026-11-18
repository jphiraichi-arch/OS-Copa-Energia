"""Atraso progressivo do login (por login e por IP), chaves HMAC e IP atrás de proxy."""

import asyncio
import logging
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from starlette.websockets import WebSocket

from osapp import cli, rede
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


def test_atraso_com_teto_proprio():
    assert atraso(100, 100) == timedelta(0)
    assert atraso(101, 100, timedelta(seconds=60)) == timedelta(seconds=2)
    assert atraso(106, 100, timedelta(seconds=60)) == timedelta(seconds=60)  # 64 s -> teto
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


# --- Por IP (CGNAT: limite alto, espera curta, nunca bloqueia) ---------------------------


def test_limites_por_ip_padrao_e_configuraveis(monkeypatch):
    monkeypatch.setattr(protecao_login, "load_dotenv", lambda: None)
    monkeypatch.delenv("OS_LIMITE_FALHAS_IP", raising=False)
    monkeypatch.delenv("OS_ATRASO_MAX_IP_SEGUNDOS", raising=False)
    assert protecao_login.falhas_livres_ip() == 100  # bem acima das 3 do login
    assert protecao_login.atraso_maximo_ip() == timedelta(seconds=60)
    monkeypatch.setenv("OS_LIMITE_FALHAS_IP", "250")
    monkeypatch.setenv("OS_ATRASO_MAX_IP_SEGUNDOS", "30")
    assert protecao_login.falhas_livres_ip() == 250
    assert protecao_login.atraso_maximo_ip() == timedelta(seconds=30)
    for valor in ("0", "-1", "abc"):
        monkeypatch.setenv("OS_LIMITE_FALHAS_IP", valor)
        with pytest.raises(ConfigError, match="OS_LIMITE_FALHAS_IP"):
            protecao_login.validar_configuracao()


@pytest.fixture
def limite_ip_baixo(monkeypatch):
    """Limite por IP pequeno só para o teste andar rápido (o padrão é 100)."""
    monkeypatch.setenv("OS_LIMITE_FALHAS_IP", "5")
    monkeypatch.setenv("OS_ATRASO_MAX_IP_SEGUNDOS", "8")


def test_limite_por_ip_em_logins_diferentes_e_outro_ip_livre(usuarios, tempo, limite_ip_baixo):
    for n in range(5):
        assert tentar(f"login.{n}", ip=IP_A) == "falha"
        tempo.avancar(seconds=10)
    assert linha(TIPO_IP, IP_A) == (5, None)
    assert tentar("login.5", ip=IP_A) == "falha"  # 6ª falha do IP: 2 s
    assert linha(TIPO_IP, IP_A) == (6, tempo.agora + timedelta(seconds=2))
    assert tentar("admin", SENHA, ip=IP_A) == "espera"  # vale para qualquer login
    assert tentar("admin", SENHA, ip=IP_B) == "ok"  # outro IP não é afetado
    tempo.avancar(seconds=2)
    assert tentar("admin", SENHA, ip=IP_A) == "ok"


def test_ip_nunca_fica_bloqueado_espera_curta(usuarios, tempo, limite_ip_baixo):
    esperas = []
    for n in range(12):
        assert tentar(f"login.{n}", ip=IP_A) == "falha"  # cada login falha só uma vez
        proximo = linha(TIPO_IP, IP_A)[1]
        espera = 0 if proximo is None else int((proximo - tempo.agora).total_seconds())
        esperas.append(espera)
        tempo.avancar(seconds=espera)  # quem espera o pouco pedido sempre consegue tentar
    assert esperas == [0, 0, 0, 0, 0, 2, 4, 8, 8, 8, 8, 8]
    assert tentar("admin", SENHA, ip=IP_A) == "ok"


def test_contador_de_ip_expirado_nao_conta(usuarios, tempo, limite_ip_baixo):
    for n in range(6):
        tentar(f"login.{n}", ip=IP_A)
    tempo.avancar(minutes=15, seconds=1)  # 15 min sem falha: o contador do IP expirou
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


# --- Limpeza (sem tarefa agendada) -----------------------------------------------------


def _quantas() -> int:
    with sessao() as s:
        return s.query(TentativaLogin).count()


def test_contador_de_login_expira_em_30_dias(usuarios, tempo):
    for _ in range(6):
        tentar("marina.teste")
    tempo.avancar(days=30, seconds=1)
    assert tentar("marina.teste") == "falha"
    assert linha(TIPO_LOGIN, "marina.teste") == (1, None)  # a contagem antiga não contou


def test_nova_tentativa_apaga_o_contador_expirado_da_chave(usuarios, tempo, monkeypatch):
    tentar("marina.teste", ip=IP_A)
    tempo.avancar(minutes=16)
    apagadas = []
    original = protecao_login.TentativaLoginRepo.apagar_expiradas

    def espiao(self, agora, limites, chave=None):
        n = original(self, agora, limites, chave)
        apagadas.append((tuple(limites), chave is not None, n))
        return n

    monkeypatch.setattr(protecao_login.TentativaLoginRepo, "apagar_expiradas", espiao)
    tentar("marina.teste", ip=IP_A)
    # Login (ainda válido): nada apagado. IP (16 min sem falha): a linha da chave sai.
    assert apagadas == [(("LOGIN",), True, 0), (("IP",), True, 1)]
    assert linha(TIPO_IP, IP_A) == (1, None)
    assert linha(TIPO_LOGIN, "marina.teste")[0] == 2


def test_varredura_ao_iniciar_apaga_so_os_expirados(usuarios, tempo):
    tentar("antigo", ip=IP_A)  # login e IP_A
    tempo.avancar(minutes=20)
    tentar("recente", ip=IP_B)  # login e IP_B
    assert _quantas() == 4
    protecao_login.limpeza_ao_iniciar()
    assert _quantas() == 3  # só o IP_A (15 min sem falha); o login 'antigo' vale 30 dias
    tempo.avancar(days=31)
    protecao_login.limpeza_ao_iniciar()
    assert _quantas() == 0


def test_espera_pendente_nao_e_apagada(usuarios, tempo):
    for _ in range(13):  # espera do login chega a 15 min
        tentar("marina.teste", ip=f"192.0.2.{_quantas()}")
        tempo.avancar(seconds=1000)
    proximo = linha(TIPO_LOGIN, "marina.teste")[1]
    assert proximo > tempo.agora - timedelta(seconds=1000)
    protecao_login.limpeza_ao_iniciar()
    assert linha(TIPO_LOGIN, "marina.teste") is not None


def test_falha_na_varredura_nao_impede_iniciar(monkeypatch, caplog):
    def quebra(_agora):
        raise RuntimeError("banco fora do ar")

    monkeypatch.setattr(protecao_login, "apagar_expiradas", quebra)
    with caplog.at_level(logging.WARNING):
        protecao_login.limpeza_ao_iniciar()  # não levanta
    assert "Limpeza de contadores" in caplog.text


def test_comando_manual_continua(usuarios, tempo, capsys):
    tentar("antigo")
    tempo.avancar(days=30, seconds=1)
    tentar("recente", ip=IP_B)
    assert cli.main(["limpar-tentativas"]) == 0
    assert "2 contador(es)" in capsys.readouterr().out  # login 'antigo' e IP_A
    assert linha(TIPO_LOGIN, "antigo") is None and linha(TIPO_LOGIN, "recente") is not None


# --- IP do cliente atrás de proxy (osapp/rede.py) ---------------------------------------

REDES = rede.ler_redes(None)  # padrão: 10.0.0.0/8 + loopback
RENDER = "10.204.1.7"  # um endereço interno do proxy (fictício)


@pytest.mark.parametrize(
    ("par", "cabecalhos", "esperado"),
    [
        # XFF forjado à esquerda é ignorado: vale o primeiro não confiável pela direita.
        (RENDER, {"x-forwarded-for": "1.2.3.4, 198.51.100.20"}, "198.51.100.20"),
        (RENDER, {"x-forwarded-for": "1.2.3.4, 198.51.100.20, 10.0.0.9"}, "198.51.100.20"),
        # True-Client-Ip tem preferência.
        (
            RENDER,
            {"true-client-ip": "198.51.100.7", "x-forwarded-for": "203.0.113.9"},
            "198.51.100.7",
        ),
        # True-Client-Ip inválido: segue para o XFF.
        (RENDER, {"true-client-ip": "abc", "x-forwarded-for": "203.0.113.9"}, "203.0.113.9"),
        # Cadeia só de endereços confiáveis: o próprio par.
        (RENDER, {"x-forwarded-for": "10.0.0.7, 127.0.0.1"}, RENDER),
        (RENDER, {}, RENDER),
        # Lixo na cadeia: não se confia no que está à esquerda dele.
        (RENDER, {"x-forwarded-for": "198.51.100.20, lixo"}, RENDER),
        # Portas e IPv6.
        (RENDER, {"x-forwarded-for": "198.51.100.20:5555"}, "198.51.100.20"),
        (RENDER, {"x-forwarded-for": "[2001:db8::1]:443"}, "2001:db8::1"),
        # Conexão direta de fora (não é proxy): nenhum cabeçalho é aceito.
        (
            "203.0.113.50",
            {"true-client-ip": "1.1.1.1", "x-forwarded-for": "2.2.2.2"},
            "203.0.113.50",
        ),
        (None, {"x-forwarded-for": "2.2.2.2"}, None),
    ],
)
def test_resolver_ip(par, cabecalhos, esperado):
    assert rede.resolver_ip(par, cabecalhos, REDES) == esperado


def test_redes_confiaveis():
    assert rede.confiavel("10.1.1.1", REDES) and rede.confiavel("127.0.0.1", REDES)
    assert rede.confiavel("::1", REDES) and not rede.confiavel("192.168.0.1", REDES)
    proprias = rede.ler_redes("172.16.0.0/12, 192.0.2.5")
    assert rede.confiavel("172.20.0.1", proprias) and rede.confiavel("127.0.0.1", proprias)
    assert not rede.confiavel("10.1.1.1", proprias)  # a variável substitui o padrão
    for invalido in ("*", "10.0.0.0/8, banana"):
        with pytest.raises(ValueError, match="OS_PROXIES_CONFIAVEIS"):
            rede.ler_redes(invalido)


async def _pela_porta(cabecalhos, par=RENDER, depurar=False, tipo="websocket"):
    """O que o Flet veria (WebSocket.client.host) depois do middleware."""
    visto = {}

    async def app(scope, receive, send):
        visto["host"] = (
            WebSocket(scope, receive, send).client.host
            if tipo == "websocket"
            else (scope["client"][0])
        )
        visto["scheme"] = scope.get("scheme")

    scope = {
        "type": tipo,
        "path": "/ws",
        "headers": [(n.encode(), v.encode()) for n, v in cabecalhos],
        "client": (par, 50000),
        "scheme": "ws" if tipo == "websocket" else "http",
    }
    await rede.ResolverIpCliente(app, REDES, depurar)(scope, None, None)
    return visto


def test_middleware_no_websocket_e_no_http():
    visto = asyncio.run(
        _pela_porta(
            [
                ("X-Forwarded-For", "1.2.3.4"),
                ("X-Forwarded-For", "198.51.100.20"),
                ("X-Forwarded-Proto", "https"),
            ]
        )
    )
    assert visto == {"host": "198.51.100.20", "scheme": "wss"}  # cabeçalho repetido somado
    visto = asyncio.run(_pela_porta([("True-Client-Ip", "198.51.100.7")], tipo="http"))
    assert visto["host"] == "198.51.100.7"
    forjado = asyncio.run(_pela_porta([("X-Forwarded-Proto", "https")], par="203.0.113.50"))
    assert forjado == {"host": "203.0.113.50", "scheme": "ws"}


def test_depuracao_desligada_por_padrao(monkeypatch, caplog):
    monkeypatch.delenv("OS_DEPURAR_CABECALHOS_IP", raising=False)
    assert rede.ResolverIpCliente(lambda *_: None).depurar is False
    with caplog.at_level(logging.DEBUG):
        asyncio.run(_pela_porta([("X-Forwarded-For", "198.51.100.20")]))
    assert "198.51.100.20" not in caplog.text
    with caplog.at_level(logging.WARNING):
        asyncio.run(_pela_porta([("X-Forwarded-For", "198.51.100.20")], depurar=True))
    assert "Depuração de IP" in caplog.text and "198.51.100.20" in caplog.text
    monkeypatch.setenv("OS_DEPURAR_CABECALHOS_IP", "1")
    assert rede.ResolverIpCliente(lambda *_: None).depurar is True


def test_inicializacao_sem_proxy_headers_do_uvicorn_e_sem_sqlite():
    script = (RAIZ / "docker" / "iniciar.sh").read_text(encoding="utf-8")
    assert "--no-proxy-headers" in script and "--no-access-log" in script
    assert "forwarded-allow-ips" not in script
    assert subprocess.run(["sh", "-n", str(RAIZ / "docker" / "iniciar.sh")]).returncode == 0
    # Com SQLite o contêiner para antes de migrar.
    resultado = subprocess.run(
        ["sh", str(RAIZ / "docker" / "iniciar.sh")],
        env={"OS_DATABASE_URL": "sqlite:///x.db", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultado.returncode == 1 and "use PostgreSQL" in resultado.stderr


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
