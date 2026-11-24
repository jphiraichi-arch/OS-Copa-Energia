"""Prompt 20: gestão de usuários pelo administrador e troca da própria senha."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from alembic import command
from sqlalchemy import MetaData, inspect, select

from osapp import cli, db
from osapp.db import sessao
from osapp.models import Usuario, UsuarioEvento
from osapp.services import administracao, relogio, usuarios
from osapp.services.auth import autenticar
from osapp.services.erros import (
    ErroAutenticacao,
    ErroConflito,
    ErroPermissao,
    ErroValidacao,
)
from osapp.ui import rotas
from osapp.ui import sessao as sessao_ui
from tests.conftest import config_alembic

SENHA = "senha-ficticia-123"
TEMP = "Temporaria-2026"
NOVA = "Nova-Senha-Boa-1"
T0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


@pytest.fixture
def p(banco, monkeypatch):
    monkeypatch.setattr(relogio, "agora", lambda: T0)
    administracao.criar_filial("1007", "Jardinópolis")
    administracao.criar_filial("2001", "Outra Filial")

    def criar(nome, login, filial, papel):
        return administracao.criar_usuario(nome, login, SENHA, filial, papel=papel).id

    return {
        "admin": criar("Ana Admin", "ana.admin", "1007", "admin"),
        "man": criar("Mário", "mario.man", "1007", "manutencao"),
        "usu": criar("Sônia", "sonia.usu", "1007", "usuario"),
        "f2": 2,
    }


def dto(p, nome):
    return usuarios.obter_usuario(p["admin"], p[nome])


def eventos(usuario_id):
    with sessao() as s:
        return [
            (e.admin_id, e.campo, e.valor_antigo, e.valor_novo)
            for e in s.scalars(
                select(UsuarioEvento)
                .where(UsuarioEvento.usuario_id == usuario_id)
                .order_by(UsuarioEvento.id)
            )
        ]


# --- Só administrador ----------------------------------------------------------------


@pytest.mark.parametrize("quem", ["man", "usu"])
def test_quem_nao_e_admin_recebe_erro_de_permissao_em_tudo(p, quem):
    alvo = p["usu"] if quem == "man" else p["man"]
    chamadas = [
        lambda a: usuarios.listar_usuarios(a),
        lambda a: usuarios.obter_usuario(a, alvo),
        lambda a: usuarios.listar_eventos_usuario(a, alvo),
        lambda a: usuarios.criar_usuario(a, "Novo", "novo.login", 1, "usuario"),
        lambda a: usuarios.alterar_usuario(a, alvo, 1, {"nome": "X"}),
        lambda a: usuarios.redefinir_senha(a, alvo, 1),
    ]
    for chamada in chamadas:
        with pytest.raises(ErroPermissao):
            chamada(p[quem])


# --- Criação ------------------------------------------------------------------------


def test_criar_usuario_com_senha_temporaria(p):
    criado = usuarios.criar_usuario(p["admin"], " Rui Silva ", "Rui.Silva", p["f2"], "usuario")
    novo, temp = criado.usuario, criado.senha_temporaria
    assert (novo.nome, novo.login, novo.filial_codigo, novo.papel, novo.ativo) == (
        "Rui Silva",
        "rui.silva",
        "2001",
        "usuario",
        True,
    )
    assert novo.deve_trocar_senha is True
    assert eventos(novo.id) == [(p["admin"], "criacao", None, "rui.silva | 2001 | usuario")]
    assert autenticar("RUI.SILVA", temp).deve_trocar_senha is True


@pytest.mark.parametrize("login", ["rui.silva", "RUI.SILVA", "  Rui.Silva  "])
def test_login_repetido_sem_diferenciar_maiusculas_e_recusado(p, login):
    usuarios.criar_usuario(p["admin"], "Rui", "Rui.Silva", 1, "usuario")
    with pytest.raises(ErroConflito):
        usuarios.criar_usuario(p["admin"], "Outro Rui", login, 1, "manutencao")


@pytest.mark.parametrize(
    ("senha", "login"),
    [("curta-123", "novo.login"), ("novo.login", "novo.login"), ("NOVO.LOGIN", "novo.login")],
)
def test_regra_de_senha_na_criacao(p, senha, login):
    """Senha digitada (linha de comando); na tela ela é gerada (prompt 34)."""
    with pytest.raises(ErroValidacao) as info, sessao() as s:
        usuarios.criar(s, None, "Novo", login, 1, "usuario", senha)
    assert info.value.mensagem == usuarios.MSG_REGRA_SENHA


# --- Alteração e último administrador ----------------------------------------------


def test_um_evento_por_campo_alterado(p):
    d = dto(p, "man")
    depois = usuarios.alterar_usuario(
        p["admin"],
        d.id,
        d.versao,
        {
            "nome": "Mário Souza",
            "filial_id": p["f2"],
            "filiais": [p["f2"]],
            "papel": "usuario",
            "ativo": True,
        },
    )
    assert (depois.nome, depois.filial_codigo, depois.papel, depois.versao) == (
        "Mário Souza",
        "2001",
        "usuario",
        d.versao + 1,
    )
    assert eventos(d.id)[1:] == [  # depois da criação (pela linha de comando)
        (p["admin"], "nome", "Mário", "Mário Souza"),
        (p["admin"], "filial padrão", "1007", "2001"),
        (p["admin"], "papel", "manutencao", "usuario"),
        (p["admin"], "filiais", "1007", "2001"),  # prompt 34
    ]
    with pytest.raises(ErroConflito):  # versão antiga
        usuarios.alterar_usuario(p["admin"], d.id, d.versao, {"nome": "Outro"})


def test_ultimo_admin_nao_se_rebaixa_nem_se_desativa(p):
    d = dto(p, "admin")
    for alteracao in ({"papel": "manutencao"}, {"papel": "usuario"}, {"ativo": False}):
        with pytest.raises(ErroValidacao) as info:
            usuarios.alterar_usuario(p["admin"], d.id, d.versao, alteracao)
        assert info.value.mensagem == usuarios.MSG_ULTIMO_ADMIN
    assert dto(p, "admin").papel == "admin"


def test_com_dois_admins_um_rebaixa_o_outro(p):
    m = dto(p, "man")
    usuarios.alterar_usuario(p["admin"], m.id, m.versao, {"papel": "admin"})
    a = dto(p, "admin")
    usuarios.alterar_usuario(p["man"], a.id, a.versao, {"papel": "manutencao"})
    assert usuarios.obter_usuario(p["man"], p["admin"]).papel == "manutencao"
    m = usuarios.obter_usuario(p["man"], p["man"])
    with pytest.raises(ErroValidacao):  # agora 'man' é o último
        usuarios.alterar_usuario(p["man"], m.id, m.versao, {"ativo": False})


def test_desativado_e_recusado_na_proxima_chamada(p):
    from osapp.services import ordens

    ordens.listar_os(p["man"])  # funciona antes
    d = dto(p, "man")
    usuarios.alterar_usuario(p["admin"], d.id, d.versao, {"ativo": False})
    with pytest.raises(ErroAutenticacao):
        ordens.listar_os(p["man"])
    with pytest.raises(ErroAutenticacao):
        autenticar("mario.man", SENHA)
    d = dto(p, "man")
    usuarios.alterar_usuario(p["admin"], d.id, d.versao, {"ativo": True})  # reativar
    assert ordens.listar_os(p["man"]).itens == ()


# --- Senhas -------------------------------------------------------------------------


def test_redefinir_senha_e_troca_obrigatoria(p):
    d = dto(p, "usu")
    gerada = usuarios.redefinir_senha(p["admin"], d.id, d.versao)
    depois, TEMP = gerada.usuario, gerada.senha_temporaria  # noqa: N806
    assert depois.deve_trocar_senha is True
    with pytest.raises(ErroAutenticacao):
        autenticar("sonia.usu", SENHA)  # a antiga não vale mais
    ator = autenticar("sonia.usu", TEMP)
    assert ator.deve_trocar_senha is True

    # Guarda de rotas: enquanto a troca estiver pendente, qualquer rota leva à troca.
    estado = sessao_ui.SessaoUI(timeout_min=30)
    sessao_ui.iniciar(estado, ator, T0, "sonia.usu")
    for rota in ("/", "/os/1", "/configuracoes", "/usuarios", "/login", "/xyz"):
        assert sessao_ui.decidir_rota(rota, estado, T0) == rotas.TROCAR_SENHA

    usuarios.trocar_propria_senha(p["usu"], TEMP, NOVA)
    assert autenticar("sonia.usu", NOVA).deve_trocar_senha is False
    estado.troca_obrigatoria = False
    assert sessao_ui.decidir_rota("/os/1", estado, T0) == "/os/1"
    assert sessao_ui.decidir_rota(rotas.TROCAR_SENHA, estado, T0) == rotas.HOME
    campos = [e[1:] for e in eventos(p["usu"])]
    assert ("senha", None, "senha redefinida") in campos
    assert ("senha", None, "senha alterada") in campos


@pytest.mark.parametrize(
    ("atual", "nova", "campo"),
    [
        ("senha-errada-xyz", NOVA, "senha_atual"),
        (SENHA, "curta-123", "senha"),  # 9 caracteres
        (SENHA, "sonia.usu", "senha"),  # igual ao login
        (SENHA, "SONIA.USU", "senha"),
        (SENHA, SENHA, "senha"),  # igual à atual
    ],
)
def test_trocar_propria_senha_recusa(p, atual, nova, campo):
    with pytest.raises(ErroValidacao) as info:
        usuarios.trocar_propria_senha(p["usu"], atual, nova)
    assert info.value.campo == campo
    assert autenticar("sonia.usu", SENHA)  # a senha não mudou


def test_historico_nunca_guarda_senha_nem_hash(p):
    d = dto(p, "usu")
    TEMP = usuarios.redefinir_senha(p["admin"], d.id, d.versao).senha_temporaria  # noqa: N806
    usuarios.trocar_propria_senha(p["usu"], TEMP, NOVA)
    with sessao() as s:
        hash_atual = s.get(Usuario, p["usu"]).senha_hash
        linhas = [
            " ".join(str(v) for v in (e.campo, e.valor_antigo, e.valor_novo))
            for e in s.scalars(select(UsuarioEvento))
        ]
    texto = "\n".join(linhas)
    for proibido in (SENHA, TEMP, NOVA, hash_atual, "$argon2"):
        assert proibido not in texto


# --- Linha de comando pelos mesmos serviços ----------------------------------------


def test_linha_de_comando_continua_e_registra_sem_admin(p, monkeypatch, capsys):
    monkeypatch.setattr(cli.getpass, "getpass", lambda _p="": TEMP)
    assert (
        cli.main(
            [
                "criar-usuario",
                "--nome",
                "Cli",
                "--login",
                "cli.user",
                "--filial",
                "1007",
                "--papel",
                "manutencao",
            ]
        )
        == 0
    )
    assert "temporária" in capsys.readouterr().out
    assert autenticar("cli.user", TEMP).deve_trocar_senha is True
    assert cli.main(["redefinir-senha", "--login", "cli.user"]) == 0
    assert cli.main(["desativar-usuario", "--login", "cli.user"]) == 0
    with sessao() as s:
        uid = s.scalars(select(Usuario.id).where(Usuario.login == "cli.user")).one()
    assert [(a, c) for a, c, _x, _y in eventos(uid)] == [
        (None, "criacao"),
        (None, "senha"),
        (None, "ativo"),
    ]
    # A regra do último administrador vale também na linha de comando.
    assert cli.main(["desativar-usuario", "--login", "ana.admin"]) == 1


# --- Migração 0009 ------------------------------------------------------------------


def test_migracao_0009_com_dados_ida_e_volta(banco_vazio):
    cfg = config_alembic()
    command.upgrade(cfg, "0008")
    db.reiniciar()
    tabelas = MetaData()
    tabelas.reflect(bind=db.obter_engine())
    with db.obter_engine().begin() as conexao:
        conexao.execute(tabelas.tables["filiais"].insert().values(id=1, codigo="1007", nome="J"))
        conexao.execute(
            tabelas.tables["usuarios"]
            .insert()
            .values(id=1, nome="Ana", login="ana", senha_hash="x", filial_id=1, papel="admin")
        )
    db.reiniciar()
    command.upgrade(cfg, "0009")
    db.reiniciar()
    with sessao() as s:
        u = s.get(Usuario, 1)
        assert (u.login, u.papel, u.deve_trocar_senha, u.versao) == ("ana", "admin", False, 1)
        s.add(UsuarioEvento(admin_id=1, usuario_id=1, data_hora=T0, campo="nome"))
    command.downgrade(cfg, "0008")
    db.reiniciar()
    insp = inspect(db.obter_engine())
    assert "usuarios_eventos" not in insp.get_table_names()
    assert not {"deve_trocar_senha", "versao"} & {c["name"] for c in insp.get_columns("usuarios")}
    command.upgrade(cfg, "head")
