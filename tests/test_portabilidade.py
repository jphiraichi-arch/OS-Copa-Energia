"""Prompt 33: configuração portátil, GET /saude e alertas de erro grave."""

from __future__ import annotations

import ast
import io
import logging
import re
import sys
import time
import tokenize
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from osapp import config, db, saude
from osapp.config import ConfigError, carregar_config
from osapp.db import sessao
from osapp.models import EmailFila, UsuarioNotificacao
from osapp.services import alertas, protecao_login, relogio
from tests.conftest import RAIZ
from tests.fabricas import nova_filial, novo_usuario

SRC = RAIZ / "src" / "osapp"
T0 = datetime(2026, 11, 24, 15, 0, tzinfo=UTC)

# --- Configuração --------------------------------------------------------------------------


def test_sem_url_padrao_e_mensagem_clara():
    with pytest.raises(ConfigError, match="OS_DATABASE_URL"):
        carregar_config({})
    with pytest.raises(ConfigError, match="OS_DB_TIMEOUT_CONEXAO_SEGUNDOS"):
        carregar_config({"OS_DATABASE_URL": "sqlite://", "OS_DB_TIMEOUT_CONEXAO_SEGUNDOS": "x"})
    c = carregar_config({"OS_DATABASE_URL": "postgresql://u@h/db"})
    assert c.db_reciclar_conexao_s == 300 and c.db_timeout_conexao_s == 10
    assert c.database_url == "postgresql+psycopg://u@h/db"


def test_segredo_obrigatorio_na_partida(monkeypatch):
    monkeypatch.delenv("OS_HMAC_SEGREDO", raising=False)
    with pytest.raises(ConfigError, match="OS_HMAC_SEGREDO"):
        protecao_login.validar_configuracao()


def test_partida_do_servidor_sai_com_mensagem(monkeypatch, capsys):
    monkeypatch.delenv("OS_DATABASE_URL", raising=False)
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: False)
    sys.modules.pop("osapp.main", None)
    with pytest.raises(SystemExit) as saida:
        import osapp.main  # noqa: F401
    assert "OS_DATABASE_URL" in str(saida.value)
    sys.modules.pop("osapp.main", None)


def _arquivos():
    return sorted(SRC.rglob("*.py"))


def test_so_config_le_o_ambiente():
    proibidos = []
    for arquivo in _arquivos():
        if arquivo.name == "config.py" and arquivo.parent == SRC:
            continue
        arvore = ast.parse(arquivo.read_text("utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Attribute) and no.attr in ("environ", "getenv"):
                proibidos.append(f"{arquivo.name}:{no.lineno}")
            if isinstance(no, ast.Name) and no.id == "load_dotenv":
                proibidos.append(f"{arquivo.name}:{no.lineno}")
    assert proibidos == []


def _docstrings(arvore) -> set[int]:
    linhas = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            corpo = no.body
            if (
                corpo
                and isinstance(corpo[0], ast.Expr)
                and isinstance(getattr(corpo[0], "value", None), ast.Constant)
            ):
                if isinstance(corpo[0].value.value, str):
                    linhas.update(range(corpo[0].lineno, corpo[0].end_lineno + 1))
    return linhas


def test_nada_de_provedor_no_codigo():
    """'render' e 'neon' (qualquer caixa) só em comentários e docstrings."""
    achados = []
    for arquivo in _arquivos():
        texto = arquivo.read_text("utf-8")
        docs = _docstrings(ast.parse(texto))
        for tok in tokenize.generate_tokens(io.StringIO(texto).readline):
            if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE):
                continue
            if tok.type == tokenize.STRING and tok.start[0] in docs:
                continue
            if re.search(r"render|neon", tok.string, re.I):
                achados.append(f"{arquivo.relative_to(SRC)}:{tok.start[0]}: {tok.string}")
    assert achados == []


def test_env_example_e_documentacao_listam_tudo():
    nomes = {v for k, v in vars(config).items() if k.startswith("VAR_")}
    exemplo = (RAIZ / ".env.example").read_text("utf-8")
    doc = (RAIZ / "docs" / "CONFIGURACAO.md").read_text("utf-8")
    assert sorted(n for n in nomes if n not in exemplo) == []
    assert sorted(n for n in nomes if n not in doc) == []


async def _main_vazio(page):  # o app Flet não é usado nestes testes
    return None


# --- /saude --------------------------------------------------------------------------------


@pytest.fixture
def cliente(banco):
    from fastapi.testclient import TestClient

    from osapp.asgi import criar_app_asgi

    saude._em_andamento = None
    return TestClient(criar_app_asgi(_main_vazio))  # sem 'with': não sobe o trabalhador


def test_saude_ok(cliente):
    r = cliente.get("/saude")
    assert r.status_code == 200 and r.json() == {"status": "ok", "banco": "ok"}
    assert r.headers["cache-control"] == "no-store"
    assert cliente.head("/saude").status_code == 200


def test_saude_banco_fora(cliente, monkeypatch):
    def quebra():
        raise OSError("host-secreto.exemplo:5432 recusou")

    monkeypatch.setattr(db, "banco_responde", quebra)
    r = cliente.get("/saude")
    assert r.status_code == 503 and r.json() == {"status": "erro", "banco": "erro"}
    assert "host-secreto" not in r.text


def test_saude_banco_lento(banco, monkeypatch):
    import asyncio

    monkeypatch.setattr(db, "banco_responde", lambda: time.sleep(3) or True)
    saude._em_andamento = None

    async def medir():
        inicio = time.monotonic()
        ok = await saude.banco_ok()
        return ok, time.monotonic() - inicio

    ok, duracao = asyncio.run(medir())
    assert ok is False and duracao < 2.5


def test_saude_banco_inalcancavel_de_verdade(banco_vazio, monkeypatch):
    from fastapi.testclient import TestClient

    from osapp.asgi import criar_app_asgi

    monkeypatch.setenv("OS_DATABASE_URL", "postgresql://u@127.0.0.1:1/nada")
    monkeypatch.setenv("OS_DB_TIMEOUT_CONEXAO_SEGUNDOS", "1")
    db.reiniciar()
    saude._em_andamento = None
    r = TestClient(criar_app_asgi(_main_vazio)).get("/saude")
    assert r.status_code == 503 and set(r.json()) == {"status", "banco"}
    db.reiniciar()


# --- Alertas -------------------------------------------------------------------------------


@pytest.fixture
def admins(banco, monkeypatch):
    relogio_ = {"agora": T0}
    monkeypatch.setattr(relogio, "agora", lambda: relogio_["agora"])
    with sessao() as s:
        f = nova_filial(s)
        a = novo_usuario(s, f, "admin.a", "Admin A", papel="admin")
        b = novo_usuario(s, f, "admin.b", "Admin B", papel="admin")
        m = novo_usuario(s, f, "man", "Manutenção", papel="manutencao")
        for u, e in ((a, "a@exemplo.com.br"), (m, "m@exemplo.com.br")):
            s.add(UsuarioNotificacao(usuario_id=u.id, email=e, email_confirmado_em=T0))
        s.add(UsuarioNotificacao(usuario_id=b.id, email="b@exemplo.com.br"))  # não confirmado
    return relogio_


def _registro_com_excecao(mensagem="falhou com senha=abc123 e joao@x.com"):
    try:
        {}["chave-secreta"]
    except KeyError:
        return logging.LogRecord(
            "osapp.x", logging.ERROR, __file__, 10, mensagem, None, sys.exc_info()
        )


def _alertas() -> list[EmailFila]:
    with sessao() as s:
        return list(s.scalars(select(EmailFila).where(EmailFila.tipo == "alerta_erro")))


def _oc(registro, instante, rota="os_detalhe"):
    return alertas.Ocorrencia(alertas.impressao_de(registro), "ERROR", rota, instante)


def test_mesmo_erro_uma_vez_por_hora(admins):
    r = _registro_com_excecao()
    assert alertas.registrar(_oc(r, T0)) == 1  # só o admin confirmado
    assert alertas.registrar(_oc(r, T0 + timedelta(minutes=30))) == 0
    assert alertas.registrar(_oc(r, T0 + timedelta(minutes=40))) == 0
    emails = _alertas()
    assert len(emails) == 1 and emails[0].destinatario == "a@exemplo.com.br"
    assert alertas.registrar(_oc(r, T0 + timedelta(minutes=61))) == 1
    assert "Ocorrências desde o último alerta: 3" in _alertas()[-1].corpo


def test_impressao_tipo_arquivo_linha():
    r = _registro_com_excecao()
    tipo, arquivo, linha = alertas.impressao_de(r).split(":")
    assert tipo == "KeyError" and arquivo == "tests/test_portabilidade.py" and linha.isdigit()
    sem = logging.LogRecord("osapp.x", logging.ERROR, "/srv/app/osapp/db.py", 7, "x", None, None)
    assert alertas.impressao_de(sem) == "ERROR:osapp/db.py:7"


def test_teto_diario(admins):
    for i in range(25):
        sem = logging.LogRecord("osapp.x", logging.ERROR, f"/a/osapp/m{i}.py", i, "x", None, None)
        alertas.registrar(_oc(sem, T0 + timedelta(minutes=i)))
    assert len(_alertas()) == alertas.MAX_EMAILS_DIA


def test_conteudo_sem_dado_sensivel(admins):
    alertas.registrar(_oc(_registro_com_excecao(), T0))
    email = _alertas()[0]
    texto = email.assunto + email.corpo
    for proibido in ("abc123", "senha", "joao@x.com", "chave-secreta", "/home/", "/srv/"):
        assert proibido not in texto
    assert "24/11/2026 12:00" in texto and "Tela/rota: os_detalhe" in texto
    assert "KeyError:tests/test_portabilidade.py:" in texto


def test_alertas_so_no_log(admins, monkeypatch):
    monkeypatch.setenv("OS_ALERTAS_EMAIL", "0")
    assert alertas.registrar(_oc(_registro_com_excecao(), T0)) == 0
    assert _alertas() == []


def test_handler_nunca_levanta_nem_entra_em_laco(admins, monkeypatch):
    h = alertas.ManipuladorAlertas()
    chamadas = []

    def quebra(oc):
        chamadas.append(oc)
        logging.getLogger("osapp.qualquer").error("erro dentro do alerta")
        raise RuntimeError("banco fora")

    monkeypatch.setattr(alertas, "registrar", quebra)
    raiz = logging.getLogger()
    raiz.addHandler(h)
    try:
        logging.getLogger("osapp.x").error("primeiro", exc_info=_registro_com_excecao().exc_info)
        for _ in range(50):
            if chamadas:
                break
            time.sleep(0.02)
        time.sleep(0.2)
        assert len(chamadas) == 1  # o erro logado dentro da thread não virou outro alerta
        # Registro estranho: emit engole.
        ruim = logging.LogRecord("osapp.x", logging.ERROR, None, None, "x", None, (None, 1, 2))
        h.emit(ruim)
        logging.getLogger("osapp.services.alertas").error("do próprio módulo")
        time.sleep(0.1)
        assert len(chamadas) == 1
    finally:
        raiz.removeHandler(h)


def test_instalado_na_partida():
    fonte = (SRC / "main.py").read_text("utf-8")
    assert "alertas.instalar()" in fonte
