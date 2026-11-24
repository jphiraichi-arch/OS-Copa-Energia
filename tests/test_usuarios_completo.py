"""Prompt 34: gestão de usuários completa (filiais permitidas, senha gerada, gancho do 35)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import pytest
from alembic import command
from sqlalchemy import MetaData, select

from osapp import db
from osapp.db import sessao
from osapp.models import Usuario, UsuarioEvento
from osapp.services import administracao, notificacoes, ordens, relogio, senhas, usuarios
from osapp.services.auth import autenticar
from osapp.services.erros import ErroNaoEncontrado, ErroPermissao, ErroValidacao
from tests.conftest import config_alembic

SENHA = "senha-ficticia-123"
T0 = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
PARECIDOS = set("0Oo1lIi")


@pytest.fixture
def p(banco, monkeypatch):
    monkeypatch.setattr(relogio, "agora", lambda: T0)
    f = {c: administracao.criar_filial(c, f"Filial {c}").id for c in ("1007", "2001", "3001")}

    def criar(nome, login, filial, papel):
        return administracao.criar_usuario(nome, login, SENHA, filial, papel=papel).id

    return {
        **f,
        "admin": criar("Ana Admin", "ana.admin", "1007", "admin"),
        "man": criar("Mário", "mario.man", "1007", "manutencao"),
        "usu": criar("Sônia", "sonia.usu", "1007", "usuario"),
    }


def _dto(p, chave):
    return usuarios.obter_usuario(p["admin"], p[chave])


# --- Senha temporária gerada ---------------------------------------------------------------


def test_senha_gerada_tamanho_e_caracteres():
    for _ in range(200):
        senha = usuarios.gerar_senha_temporaria()
        assert len(senha) >= 12 and not PARECIDOS & set(senha)
        assert set(senha) <= set(usuarios.ALFABETO_TEMPORARIA)
        assert any(c.isdigit() for c in senha) and any(c.isupper() for c in senha)
        usuarios.validar_senha_nova(senha, "qualquer.login")


def test_criar_mostra_a_senha_uma_vez_e_guarda_so_o_hash(p, caplog):
    with caplog.at_level(logging.DEBUG):
        gerada = usuarios.criar_usuario(
            p["admin"], "Rui", "rui.man", p["1007"], "manutencao", [p["1007"], p["2001"]]
        )
    senha = gerada.senha_temporaria
    assert senha not in repr(gerada) and "***" in repr(gerada)
    assert senha not in caplog.text
    with sessao() as s:
        u = s.get(Usuario, gerada.usuario.id)
        assert u.senha_hash != senha and u.senha_hash.startswith("$argon2id$")
        assert senhas.verificar(senha, u.senha_hash) and u.deve_trocar_senha is True
        eventos = " ".join(
            f"{e.valor_antigo} {e.valor_novo}"
            for e in s.scalars(select(UsuarioEvento).where(UsuarioEvento.usuario_id == u.id))
        )
    assert senha not in eventos
    # Nenhuma leitura posterior devolve a senha.
    assert not any(senha in str(v) for v in vars(usuarios.obter_usuario(p["admin"], u.id)).values())
    assert autenticar("rui.man", senha).deve_trocar_senha is True


def test_redefinir_gera_outra_senha_e_marca_troca(p, caplog):
    d = _dto(p, "man")
    with caplog.at_level(logging.DEBUG):
        gerada = usuarios.redefinir_senha(p["admin"], d.id, d.versao)
    assert gerada.senha_temporaria not in caplog.text
    assert gerada.usuario.deve_trocar_senha is True
    assert autenticar("mario.man", gerada.senha_temporaria).deve_trocar_senha is True
    with pytest.raises(ErroPermissao):
        usuarios.redefinir_senha(p["man"], p["usu"], 1)


# --- Filiais permitidas --------------------------------------------------------------------


def test_criar_com_filiais_e_padrao(p):
    u = usuarios.criar_usuario(
        p["admin"], "Rui", "rui.man", p["2001"], "manutencao", [p["1007"], p["2001"]]
    ).usuario
    assert (u.filial_codigo, u.filiais_codigos) == ("2001", ("1007", "2001"))
    with pytest.raises(ErroValidacao) as erro:
        usuarios.criar_usuario(p["admin"], "X", "x.man", p["3001"], "manutencao", [p["1007"]])
    assert erro.value.mensagem == usuarios.MSG_FILIAL_PADRAO
    with pytest.raises(ErroValidacao) as erro:
        usuarios.criar_usuario(p["admin"], "Y", "y.man", p["1007"], "manutencao", [])
    assert erro.value.campo == "filiais"


def test_editar_filiais_padrao_sempre_entre_elas(p):
    d = _dto(p, "man")
    depois = usuarios.alterar_usuario(
        p["admin"], d.id, d.versao, {"filiais": [p["1007"], p["3001"]]}
    )
    assert depois.filiais_codigos == ("1007", "3001")
    with pytest.raises(ErroValidacao):  # tirar a padrão
        usuarios.alterar_usuario(p["admin"], d.id, depois.versao, {"filiais": [p["3001"]]})
    with pytest.raises(ErroValidacao):  # nenhuma
        usuarios.alterar_usuario(p["admin"], d.id, depois.versao, {"filiais": []})
    with pytest.raises(ErroValidacao):  # padrão fora das permitidas
        usuarios.alterar_usuario(p["admin"], d.id, depois.versao, {"filial_id": p["2001"]})
    agora = _dto(p, "man")
    trocado = usuarios.alterar_usuario(
        p["admin"], d.id, agora.versao, {"filial_id": p["3001"], "filiais": [p["3001"]]}
    )
    assert (trocado.filial_codigo, trocado.filiais_codigos) == ("3001", ("3001",))
    with sessao() as s:
        campos = [
            (e.campo, e.valor_antigo, e.valor_novo)
            for e in s.scalars(select(UsuarioEvento).where(UsuarioEvento.usuario_id == d.id))
        ]
    assert ("filiais", "1007", "1007, 3001") in campos
    assert ("filiais", "1007, 3001", "3001") in campos
    assert ("filial padrão", "1007", "3001") in campos


def test_acesso_segue_as_filiais_permitidas(p):
    d = _dto(p, "man")
    usuarios.alterar_usuario(p["admin"], d.id, d.versao, {"filiais": [p["1007"], p["2001"]]})
    em_2001 = ordens.criar_solicitacao(p["admin"], "Na 2001", "Descrição.", "alta", p["2001"])
    em_3001 = ordens.criar_solicitacao(p["admin"], "Na 3001", "Descrição.", "alta", p["3001"])
    vistos = {o.id for o in ordens.listar_os(p["man"]).itens}
    assert em_2001.id in vistos and em_3001.id not in vistos
    assert ordens.obter_os(p["man"], em_2001.id).id == em_2001.id
    with pytest.raises(ErroNaoEncontrado):
        ordens.obter_os(p["man"], em_3001.id)
    assert {f.codigo for f in ordens.listar_filiais(p["man"])} == {"1007", "2001"}
    assert ordens.contadores(p["man"]).filial_rotulo == "Filiais 1007, 2001"
    assert ordens.contadores(p["man"], p["2001"]).abertas == 1
    with pytest.raises(ErroPermissao):
        ordens.listar_os(p["man"], filial_id=p["3001"])
    criada = ordens.criar_solicitacao(p["man"], "Pela manutenção", "Descrição.", "baixa", p["2001"])
    assert ordens.obter_os(p["admin"], criada.id).filial_id == p["2001"]
    with pytest.raises(ErroPermissao):
        ordens.criar_solicitacao(p["man"], "Fora", "Descrição.", "baixa", p["3001"])


def test_destinatario_de_email_em_varias_filiais():
    assert notificacoes.recebe("manutencao", (1, 2), "baixa", 2, "alta")
    assert not notificacoes.recebe("manutencao", (1, 2), "baixa", 3, "alta")


def test_lista_mostra_filiais_padrao_e_filtra_pela_permitida(p):
    d = _dto(p, "man")
    usuarios.alterar_usuario(p["admin"], d.id, d.versao, {"filiais": [p["1007"], p["2001"]]})
    lista = usuarios.listar_usuarios(p["admin"], filial_id=p["2001"])
    assert [u.login for u in lista] == ["mario.man"]
    assert lista[0].filiais_codigos == ("1007", "2001") and lista[0].filial_codigo == "1007"
    from osapp.ui.views.usuarios import texto_filiais

    assert texto_filiais(("1007", "2001"), "1007") == "1007 (padrão), 2001"


# --- Gancho do prompt 35 -------------------------------------------------------------------


def test_reset_troca_e_desativacao_revogam_sessoes_lembradas(p, monkeypatch):
    from osapp.services import sessoes_lembradas

    chamados: list[int] = []
    monkeypatch.setattr(
        sessoes_lembradas,
        "revogar_sessoes_lembradas",
        lambda uid, s=None: chamados.append(uid) or 0,
    )
    d = _dto(p, "man")
    temp = usuarios.redefinir_senha(p["admin"], d.id, d.versao).senha_temporaria
    usuarios.trocar_propria_senha(p["man"], temp, "Nova-Senha-Boa-1")
    d = _dto(p, "man")
    usuarios.alterar_usuario(p["admin"], d.id, d.versao, {"nome": "Mário S."})  # não revoga
    d = _dto(p, "man")
    usuarios.alterar_usuario(p["admin"], d.id, d.versao, {"ativo": False})
    assert chamados == [p["man"]] * 3


# --- Migração 0015 -----------------------------------------------------------------------


def test_migracao_0015_com_dados(banco_vazio):
    cfg = config_alembic()
    command.upgrade(cfg, "0014")
    db.reiniciar()
    m = MetaData()
    m.reflect(bind=db.obter_engine())
    with db.obter_engine().begin() as c:
        c.execute(m.tables["filiais"].insert().values(id=1, codigo="1007", nome="A"))
        c.execute(m.tables["filiais"].insert().values(id=2, codigo="2001", nome="B"))
        for uid, filial in ((1, 1), (2, 2)):
            c.execute(
                m.tables["usuarios"]
                .insert()
                .values(
                    id=uid,
                    nome=f"U{uid}",
                    login=f"u{uid}",
                    senha_hash="x",
                    filial_id=filial,
                    papel="manutencao",
                    versao=1,
                )
            )
    command.upgrade(cfg, "0015")
    m2 = MetaData()
    m2.reflect(bind=db.obter_engine())
    with db.obter_engine().connect() as c:
        pares = sorted(c.execute(select(m2.tables["usuario_filiais"])).all())
    assert pares == [(1, 1), (2, 2)]
    command.downgrade(cfg, "0014")
    m3 = MetaData()
    m3.reflect(bind=db.obter_engine())
    assert "usuario_filiais" not in m3.tables
    with db.obter_engine().connect() as c:
        assert c.execute(select(m3.tables["usuarios"].c.filial_id)).scalars().all() == [1, 2]
    command.upgrade(cfg, "head")
