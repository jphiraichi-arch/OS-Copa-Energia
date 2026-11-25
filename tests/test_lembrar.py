"""Prompt 35: 'Lembrar de mim por 7 dias' (tokens com hash, rotação e revogação)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import select

from osapp import db
from osapp.db import sessao
from osapp.models import SessaoLembrada
from osapp.services import administracao, relogio, usuarios
from osapp.services import sessoes_lembradas as sl
from osapp.services.auth import autenticar
from osapp.services.erros import ErroAutenticacao, ErroMuitasTentativas, ErroPermissao
from tests.conftest import config_alembic

SENHA = "senha-ficticia-123"
T0 = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
UA_ANDROID = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0 Mobile Safari/537.36"
)
UA_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1"
)


class Relogio:
    def __init__(self):
        self.agora = T0

    def __call__(self):
        return self.agora


@pytest.fixture
def r(monkeypatch):
    relogio_ = Relogio()
    monkeypatch.setattr(relogio, "agora", relogio_)
    return relogio_


@pytest.fixture
def p(banco, r):
    administracao.criar_filial("1007", "Jardinópolis")

    def criar(nome, login, papel):
        return administracao.criar_usuario(nome, login, SENHA, "1007", papel=papel).id

    return {
        "admin": criar("Ana Admin", "ana.admin", "admin"),
        "man": criar("Mário", "mario.man", "manutencao"),
        "usu": criar("Sônia", "sonia.usu", "usuario"),
    }


def _linhas():
    with sessao() as s:
        return list(s.scalars(select(SessaoLembrada).order_by(SessaoLembrada.id)))


# --- Criação --------------------------------------------------------------------------


def test_sem_a_caixa_nenhum_token(p):
    autenticar("mario.man", SENHA)
    assert _linhas() == []


def test_so_o_hash_e_nada_no_log(p, caplog):
    with caplog.at_level(logging.DEBUG):
        emitido = sl.lembrar(p["man"], UA_ANDROID)
        sl.entrar_com_token(emitido.token)
    linha = _linhas()[0]
    assert linha.token_hash == sl.hash_token(emitido.token) and len(linha.token_hash) == 64
    assert emitido.token not in linha.token_hash
    assert linha.rotulo_aparelho == "Chrome em Android" and "Mozilla" not in linha.rotulo_aparelho
    assert linha.expira_em == T0 + timedelta(days=7)
    assert emitido.token not in caplog.text and "***" in repr(emitido)
    assert len(emitido.token) >= 43


@pytest.mark.parametrize(
    ("ua", "rotulo"),
    [
        (UA_ANDROID, "Chrome em Android"),
        (UA_IPHONE, "Safari em iPhone"),
        ("Mozilla/5.0 (Windows NT 10.0) Gecko/20100101 Firefox/133.0", "Firefox em Windows"),
        ("Mozilla/5.0 (Windows NT 10.0) Chrome/131.0 Safari/537.36 Edg/131.0", "Edge em Windows"),
        (
            "Mozilla/5.0 (Linux; Android 14) SamsungBrowser/26.0 Chrome/122",
            "Samsung Internet em Android",
        ),
        (None, "Navegador"),
        ("", "Navegador"),
    ],
)
def test_rotulo_do_aparelho(ua, rotulo):
    assert sl.rotulo_aparelho(ua) == rotulo


# --- Uso e rotação ------------------------------------------------------------------------


def test_token_valido_entra_e_e_trocado_com_a_mesma_validade(p, r):
    emitido = sl.lembrar(p["man"], UA_ANDROID)
    r.agora = T0 + timedelta(hours=5)
    entrada = sl.entrar_com_token(emitido.token)
    assert entrada.ator.usuario_id == p["man"]
    assert entrada.emitido.token != emitido.token
    assert entrada.emitido.familia == emitido.familia
    antigo, novo = _linhas()
    assert antigo.ultimo_uso_em == r.agora and novo.ultimo_uso_em is None
    assert novo.expira_em == antigo.expira_em == T0 + timedelta(days=7)


def test_expirado_revogado_e_desativado_sao_recusados(p, r):
    a = sl.lembrar(p["man"], UA_ANDROID)
    r.agora = T0 + timedelta(days=7)
    with pytest.raises(ErroAutenticacao):
        sl.entrar_com_token(a.token)
    r.agora = T0
    b = sl.lembrar(p["man"], UA_ANDROID)
    sl.sair_deste_aparelho(p["man"], b.familia)
    with pytest.raises(ErroAutenticacao):
        sl.entrar_com_token(b.token)
    c = sl.lembrar(p["usu"], UA_IPHONE)
    with sessao() as s:
        from osapp.models import Usuario

        s.get(Usuario, p["usu"]).ativo = False
    with pytest.raises(ErroAutenticacao):
        sl.entrar_com_token(c.token)
    for lixo in ("", "x" * 500, None, 123, "nao-existe"):
        with pytest.raises(ErroAutenticacao):
            sl.entrar_com_token(lixo)


def test_token_ja_trocado_usado_de_novo_revoga_a_familia(p, caplog):
    a = sl.lembrar(p["man"], UA_ANDROID)
    outra = sl.lembrar(p["man"], UA_IPHONE)  # outro aparelho: não é afetado
    b = sl.entrar_com_token(a.token).emitido  # o legítimo usou e trocou
    with caplog.at_level(logging.WARNING), pytest.raises(ErroAutenticacao):
        sl.entrar_com_token(a.token)  # a cópia
    assert "SEGURANÇA" in caplog.text and a.familia in caplog.text
    assert a.token not in caplog.text and b.token not in caplog.text
    with pytest.raises(ErroAutenticacao):
        sl.entrar_com_token(b.token)  # o legítimo também perdeu: a família caiu
    assert sl.entrar_com_token(outra.token).ator.usuario_id == p["man"]


def test_depois_de_7_dias_a_senha_volta_mesmo_com_uso_continuo(p, r):
    token = sl.lembrar(p["man"], UA_ANDROID).token
    for horas in range(0, 7 * 24, 6):
        r.agora = T0 + timedelta(hours=horas)
        token = sl.entrar_com_token(token).emitido.token
    r.agora = T0 + timedelta(days=7, seconds=1)
    with pytest.raises(ErroAutenticacao):
        sl.entrar_com_token(token)


def test_tokens_invalidos_contam_no_limite_por_ip(p, monkeypatch):
    monkeypatch.setenv("OS_LIMITE_FALHAS_IP", "3")
    for _ in range(4):
        with pytest.raises(ErroAutenticacao):
            sl.entrar_com_token("token-falso", "203.0.113.9")
    with pytest.raises(ErroMuitasTentativas):
        sl.entrar_com_token("token-falso", "203.0.113.9")
    bom = sl.lembrar(p["man"], UA_ANDROID)
    with pytest.raises(ErroMuitasTentativas):  # o IP está em espera: nem o válido entra
        sl.entrar_com_token(bom.token, "203.0.113.9")
    assert sl.entrar_com_token(bom.token, "198.51.100.1").ator.usuario_id == p["man"]


# --- Revogação ----------------------------------------------------------------------------


def test_troca_redefinicao_e_desativacao_revogam_tudo(p):
    t1 = sl.lembrar(p["man"], UA_ANDROID).token
    usuarios.trocar_propria_senha(p["man"], SENHA, "Nova-Senha-Boa-1")
    with pytest.raises(ErroAutenticacao):
        sl.entrar_com_token(t1)
    t2 = sl.lembrar(p["man"], UA_ANDROID).token
    d = usuarios.obter_usuario(p["admin"], p["man"])
    usuarios.redefinir_senha(p["admin"], d.id, d.versao)
    with pytest.raises(ErroAutenticacao):
        sl.entrar_com_token(t2)
    t3 = sl.lembrar(p["man"], UA_ANDROID).token
    d = usuarios.obter_usuario(p["admin"], p["man"])
    usuarios.alterar_usuario(p["admin"], d.id, d.versao, {"ativo": False})
    with pytest.raises(ErroAutenticacao):
        sl.entrar_com_token(t3)
    assert all(x.revogado_em is not None for x in _linhas())


def test_sair_de_todos_so_do_proprio_usuario(p):
    meus = [sl.lembrar(p["man"], ua).token for ua in (UA_ANDROID, UA_IPHONE)]
    dela = sl.lembrar(p["usu"], UA_IPHONE).token
    assert len(sl.listar_aparelhos(p["man"])) == 2
    assert sl.sair_de_todos(p["man"]) == 2
    for token in meus:
        with pytest.raises(ErroAutenticacao):
            sl.entrar_com_token(token)
    assert sl.entrar_com_token(dela).ator.usuario_id == p["usu"]
    assert sl.listar_aparelhos(p["man"]) == []


def test_aparelhos_conectados_e_sair_deste(p, r):
    a = sl.lembrar(p["man"], UA_ANDROID)
    r.agora = T0 + timedelta(hours=1)
    b = sl.lembrar(p["man"], UA_IPHONE)
    r.agora = T0 + timedelta(hours=2)
    sl.entrar_com_token(a.token)
    lista = sl.listar_aparelhos(p["man"])
    assert [x.rotulo for x in lista] == ["Chrome em Android", "Safari em iPhone"]
    android = lista[0]
    assert android.criado_em == T0 and android.ultimo_uso_em == T0 + timedelta(hours=2)
    from osapp.services.erros import ErroNaoEncontrado

    with pytest.raises(ErroNaoEncontrado):  # não sai do aparelho de outra pessoa
        sl.sair_deste_aparelho(p["usu"], b.familia)
    sl.sair_deste_aparelho(p["man"], b.familia)
    assert [x.rotulo for x in sl.listar_aparelhos(p["man"])] == ["Chrome em Android"]


def test_administrador_revoga_os_aparelhos_de_um_usuario(p):
    t = sl.lembrar(p["man"], UA_ANDROID).token
    with pytest.raises(ErroPermissao):
        sl.revogar_de_usuario(p["usu"], p["man"])
    assert sl.revogar_de_usuario(p["admin"], p["man"]) == 1
    with pytest.raises(ErroAutenticacao):
        sl.entrar_com_token(t)


def test_limpeza_apaga_expirados_e_revogados_com_mais_de_30_dias(p, r):
    a = sl.lembrar(p["man"], UA_ANDROID)
    sl.lembrar(p["usu"], UA_IPHONE)
    sl.sair_deste_aparelho(p["man"], a.familia)
    assert sl.limpar(T0 + timedelta(days=29)) == 0
    assert sl.limpar(T0 + timedelta(days=31)) == 1  # o revogado
    assert sl.limpar(T0 + timedelta(days=38)) == 1  # o expirado (7 + 30 dias)
    assert _linhas() == []


# --- Interface (funções puras) ------------------------------------------------------------


def test_caixa_desmarcada_e_dica():
    from osapp.ui.views import login

    assert login.ROTULO_LEMBRAR == "Lembrar de mim por 7 dias"
    assert login.DICA_LEMBRAR == "Não marque em aparelhos compartilhados."
    assert login.LEMBRAR_PADRAO is False


def test_decisao_de_retomar_com_token():
    from osapp.ui import sessao as sessao_ui

    estado = sessao_ui.SessaoUI(timeout_min=30)
    assert sessao_ui.deve_tentar_token(estado, T0, ja_tentou=False)
    assert not sessao_ui.deve_tentar_token(estado, T0, ja_tentou=True)


# --- Migração ---------------------------------------------------------------------------


def test_migracao_0016_com_dados(p):
    sl.lembrar(p["man"], UA_ANDROID)
    cfg = config_alembic()
    command.downgrade(cfg, "0015")
    db.reiniciar()
    from sqlalchemy import inspect

    assert "sessoes_lembradas" not in inspect(db.obter_engine()).get_table_names()
    assert autenticar("mario.man", SENHA).usuario_id == p["man"]  # o resto continua
    command.upgrade(cfg, "head")
    db.reiniciar()
    assert _linhas() == []


def test_linha_do_aparelho_marca_este():
    from osapp.ui.views.aparelhos import linha_do_aparelho

    a = sl.Aparelho("f", "Chrome em Android", T0, T0, T0)
    assert linha_do_aparelho(a, True).atual is True  # prompt 43: dados da linha
    assert linha_do_aparelho(a, False).rotulo == "Chrome em Android"
