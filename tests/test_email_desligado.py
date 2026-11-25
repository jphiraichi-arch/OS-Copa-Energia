"""Prompt 46: e-mail escondido na interface e desligado por configuração.

OS_EMAIL_HABILITADO (padrão 0): o trabalhador da fila não sobe, nada entra em email_fila
(avisos de solicitação, códigos de confirmação, alertas de erro grave) e nenhuma conexão
com servidor de e-mail é tentada. Com 1, tudo funciona como antes (os testes de
tests/test_notificacoes_email.py e os de alerta de tests/test_portabilidade.py ligam).
"""

from __future__ import annotations

import ast
import logging
import smtplib
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from osapp import config
from osapp.db import sessao
from osapp.models import EmailFila, UsuarioNotificacao
from osapp.services import alertas, fila_email, notificacoes, ordens, relogio
from osapp.services.erros import ErroValidacao
from tests.conftest import RAIZ
from tests.fabricas import nova_filial, novo_usuario

T0 = datetime(2026, 11, 24, 15, 0, tzinfo=UTC)


# --- Interface: nenhuma menção a e-mail --------------------------------------------------


def _docstrings(arvore) -> set[int]:
    ids = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            corpo = no.body
            if (
                corpo
                and isinstance(corpo[0], ast.Expr)
                and isinstance(corpo[0].value, ast.Constant)
            ):
                ids.add(id(corpo[0].value))
    return ids


def _textos_da_interface() -> list[tuple[str, str]]:
    """Todo texto (constante de string que não é docstring) dos módulos de src/osapp/ui."""
    achados = []
    for arquivo in sorted((RAIZ / "src" / "osapp" / "ui").rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        docs = _docstrings(arvore)
        for no in ast.walk(arvore):
            if isinstance(no, ast.Constant) and isinstance(no.value, str) and id(no) not in docs:
                achados.append((f"{arquivo.relative_to(RAIZ)}:{no.lineno}", no.value))
    return achados


def _menciona_email(texto: str) -> bool:
    baixo = texto.lower()
    return "e-mail" in baixo or "notificações por e-mail" in baixo


def test_nenhum_texto_da_interface_fala_de_email():
    assert [local for local, texto in _textos_da_interface() if _menciona_email(texto)] == []


def test_guia_rapido_nao_fala_de_email():
    guia = (RAIZ / "docs" / "guia" / "guia.yaml").read_text(encoding="utf-8")
    assert not _menciona_email(guia)
    assert "fila_email" not in guia


def test_rota_da_fila_de_emails_nao_existe_mais():
    from osapp.ui import rotas
    from osapp.ui.views.perfil import itens_do_perfil

    assert rotas.resolver("/perfil/fila-email") is None  # desconhecida: vai para o início
    assert rotas.normalizar("/perfil/fila-email") == rotas.HOME
    for papel in ("usuario", "manutencao", "admin"):
        assert "fila_email" not in itens_do_perfil(papel)


# --- Configuração --------------------------------------------------------------------------


def test_padrao_desligado(monkeypatch):
    monkeypatch.delenv("OS_EMAIL_HABILITADO", raising=False)
    assert config.email_habilitado() is False
    for valor, esperado in (("0", False), ("", False), ("sim", False), ("1", True)):
        monkeypatch.setenv("OS_EMAIL_HABILITADO", valor)
        assert config.email_habilitado() is esperado


@pytest.fixture
def sem_conexao(monkeypatch):
    """Qualquer tentativa de falar com um servidor de e-mail falha o teste."""

    def proibido(*_a, **_k):
        raise AssertionError("tentou conectar ao servidor de e-mail")

    monkeypatch.setattr(smtplib, "SMTP", proibido)
    monkeypatch.setattr(smtplib, "SMTP_SSL", proibido)
    monkeypatch.setattr(fila_email, "Trabalhador", proibido)
    monkeypatch.delenv("OS_EMAIL_HABILITADO", raising=False)


def test_desligado_o_trabalhador_nao_sobe(sem_conexao, caplog):
    from fastapi.testclient import TestClient

    from osapp.asgi import criar_app_asgi

    async def main(_page):  # nenhuma sessão de navegador é aberta neste teste
        return None

    with caplog.at_level(logging.INFO, logger="osapp.asgi"), TestClient(criar_app_asgi(main)):
        pass
    assert "E-mail desligado" in caplog.text


@pytest.fixture
def pessoas(banco, monkeypatch):
    monkeypatch.setattr(relogio, "agora", lambda: T0)
    with sessao() as s:
        f = nova_filial(s, "1007", "Jardinópolis")
        ids = {
            "admin": novo_usuario(s, f, "ana.ribeiro", "Ana Ribeiro", papel="admin").id,
            "man": novo_usuario(s, f, "bruno.lima", "Bruno Lima", papel="manutencao").id,
            "sol": novo_usuario(s, f, "carla.souza", "Carla Souza", papel="usuario").id,
        }
        for chave, endereco in (("admin", "ana@exemplo.com.br"), ("man", "bruno@exemplo.com.br")):
            s.add(
                UsuarioNotificacao(
                    usuario_id=ids[chave],
                    email=endereco,
                    email_confirmado_em=T0,
                    notificacoes_ativas=True,
                    urgencia_minima="baixa",
                )
            )
    return ids


def _linhas_na_fila() -> int:
    with sessao() as s:
        return int(s.scalar(select(func.count()).select_from(EmailFila)))


def test_desligado_solicitacao_nao_entra_na_fila(pessoas, sem_conexao):
    ordens.criar_solicitacao(pessoas["sol"], "Vazamento", "Óleo no piso.", "emergencial")
    assert _linhas_na_fila() == 0


def test_ligado_a_mesma_solicitacao_entra_na_fila(pessoas, monkeypatch):
    monkeypatch.setenv("OS_EMAIL_HABILITADO", "1")
    ordens.criar_solicitacao(pessoas["sol"], "Vazamento", "Óleo no piso.", "emergencial")
    assert _linhas_na_fila() == 2  # o controle: o teste acima não passa por acaso


def test_desligado_codigo_de_confirmacao_e_recusado(pessoas, sem_conexao):
    with pytest.raises(ErroValidacao) as erro:
        notificacoes.enviar_codigo(pessoas["man"], "outro@exemplo.com.br")
    assert erro.value.mensagem == notificacoes.MSG_EMAIL_DESLIGADO
    assert _linhas_na_fila() == 0


def test_desligado_erro_grave_vai_so_para_o_log(pessoas, sem_conexao, caplog):
    registro = logging.LogRecord(
        "osapp.x", logging.ERROR, "/a/osapp/m.py", 1, "falha grave", None, None
    )
    ocorrencia = alertas.Ocorrencia(alertas.impressao_de(registro), "ERROR", "home", T0)
    assert alertas.registrar(ocorrencia) == 0
    assert _linhas_na_fila() == 0
    with caplog.at_level(logging.ERROR):
        logging.getLogger("osapp.x").error("falha grave")
    assert "falha grave" in caplog.text  # o log do servidor continua


def test_desligado_cli_nao_conecta(sem_conexao, banco, capsys):
    from osapp import cli

    assert cli.main(["enviar-fila-email"]) == 0
    assert "E-mail desligado" in capsys.readouterr().out
