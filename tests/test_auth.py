import logging
from datetime import UTC, datetime, timedelta

import pytest
from argon2 import PasswordHasher

from osapp import cli, seed
from osapp.db import sessao
from osapp.models import Filial, TentativaLogin, Usuario
from osapp.repositories import UsuarioRepo
from osapp.services import administracao, permissoes, relogio, senhas
from osapp.services.auth import Ator, autenticar, carregar_ator
from osapp.services.erros import (
    ErroAutenticacao,
    ErroConflito,
    ErroDominio,
    ErroNaoEncontrado,
    ErroPermissao,
    ErroValidacao,
)

SENHA = "senha-ficticia-123"
T0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


@pytest.fixture
def usuarios(banco):
    administracao.criar_filial("F001", "Filial Modelo Norte")
    administracao.criar_filial("F002", "Filial Modelo Sul")
    marina = administracao.criar_usuario("Marina Teste", "marina.teste", SENHA, "F001")
    admin = administracao.criar_usuario("Administrador Fictício", "admin", SENHA, "F001", True)
    carlos = administracao.criar_usuario("Carlos Exemplo", "carlos.exemplo", SENHA, "F002")
    return {"marina": marina.id, "admin": admin.id, "carlos": carlos.id}


def _usuario(login="marina.teste") -> Usuario:
    with sessao() as s:
        return UsuarioRepo(s).obter_por_login(login)


def _falhar(vezes, login="marina.teste"):
    for _ in range(vezes):
        with pytest.raises(ErroAutenticacao):
            autenticar(login, "senha-errada")


# --- senhas ---------------------------------------------------------------------------


def test_hash_e_argon2id_e_nao_contem_a_senha(usuarios):
    h = _usuario().senha_hash
    assert h.startswith("$argon2id$")
    assert SENHA not in h
    assert senhas.verificar(SENHA, h) and not senhas.verificar("outra", h)
    assert not senhas.verificar(SENHA, "isto-nao-e-um-hash")
    assert senhas.gerar_hash(SENHA) != senhas.gerar_hash(SENHA)  # sal aleatório
    assert not senhas.precisa_rehash(h)
    assert senhas.precisa_rehash("isto-nao-e-um-hash")


# --- autenticar -----------------------------------------------------------------------


def test_login_correto_devolve_o_ator(usuarios):
    ator = autenticar("  Marina.TESTE ", SENHA)
    with sessao() as s:
        f1 = s.query(Filial).filter_by(codigo="F001").one().id
    assert ator == Ator(
        usuarios["marina"], "Marina Teste", f1, "F001", "manutencao", filiais_permitidas=(f1,)
    )
    assert autenticar("admin", SENHA).e_admin is True
    assert autenticar("carlos.exemplo", SENHA).filial_codigo == "F002"


def test_falhas_sao_indistinguiveis(usuarios):
    administracao.desativar_usuario("carlos.exemplo")
    erros = []
    for login, senha in [
        ("marina.teste", "senha-errada"),
        ("nao.existe", SENHA),
        ("carlos.exemplo", SENHA),  # inativo, senha certa
        ("", SENHA),
        ("marina.teste", ""),
    ]:
        with pytest.raises(ErroAutenticacao) as info:
            autenticar(login, senha)
        erros.append(info.value)
    assert {type(e) for e in erros} == {ErroAutenticacao}
    assert len({str(e) for e in erros}) == 1
    assert len({e.args for e in erros}) == 1


def test_login_inexistente_ainda_verifica_um_hash(usuarios, monkeypatch):
    chamadas = []
    original = senhas.verificar
    monkeypatch.setattr(senhas, "verificar", lambda s, h: chamadas.append(h) or original(s, h))
    with pytest.raises(ErroAutenticacao):
        autenticar("nao.existe", SENHA)
    assert len(chamadas) == 1 and chamadas[0].startswith("$argon2id$")


def test_falha_de_um_usuario_nao_afeta_outro(usuarios, monkeypatch):
    monkeypatch.setattr(relogio, "agora", lambda: T0)
    _falhar(6)  # marina.teste fica com espera; o IP (desconhecido) ainda não
    assert autenticar("admin", SENHA)


@pytest.mark.parametrize(
    ("login", "senha"),
    [("a" * 51, SENHA), ("marina.teste", "s" * 129), (None, SENHA), ("marina.teste", 123)],
)
def test_entrada_longa_ou_invalida_e_recusada_antes_de_qualquer_hash(
    usuarios, monkeypatch, login, senha
):
    def proibido(*_a, **_k):
        raise AssertionError("não deveria calcular hash")

    monkeypatch.setattr(senhas, "verificar", proibido)
    monkeypatch.setattr(senhas, "gerar_hash", proibido)
    with pytest.raises(ErroAutenticacao):
        autenticar(login, senha)
    with sessao() as s:
        assert s.query(TentativaLogin).count() == 0  # nem conta como falha


def test_tamanhos_no_limite_sao_aceitos(usuarios):
    administracao.criar_usuario("Limite", "l" * 50, "s" * 128, "F001")
    assert autenticar("l" * 50, "s" * 128)


def test_rehash_quando_os_parametros_mudam(usuarios):
    fraco = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash(SENHA)
    with sessao() as s:
        UsuarioRepo(s).obter_por_login("marina.teste").senha_hash = fraco
    assert senhas.precisa_rehash(fraco)
    autenticar("marina.teste", SENHA)
    novo = _usuario().senha_hash
    assert novo != fraco and not senhas.precisa_rehash(novo)
    assert autenticar("marina.teste", SENHA)


def test_logs_nao_contem_senha_hash_nem_login_digitado(usuarios, caplog):
    caplog.set_level(logging.DEBUG)
    hash_marina = _usuario().senha_hash
    senha_no_login = "minha-senha-no-campo-errado"
    with pytest.raises(ErroAutenticacao):
        autenticar("marina.teste", "senha-errada-xyz")
    with pytest.raises(ErroAutenticacao):
        autenticar(senha_no_login, "qualquer-coisa-abc")
    autenticar("marina.teste", SENHA)

    texto = caplog.text + "".join(str(r.args) for r in caplog.records)
    for proibido in (
        SENHA,
        "senha-errada-xyz",
        "qualquer-coisa-abc",
        senha_no_login,
        hash_marina,
        "$argon2",
    ):
        assert proibido not in texto
    mensagens = [r.getMessage() for r in caplog.records if r.name == "osapp.services.auth"]
    falhas = [m for m in mensagens if "Falha de autenticação" in m]
    # A falha registra só as chaves HMAC: igual para login que existe e que não existe.
    assert len(falhas) == 2 and all("login=" in m and "usuario_id" not in m for m in falhas)
    assert any(f"Login bem-sucedido: usuario_id={usuarios['marina']}" in m for m in mensagens)


# --- carregar_ator e permissões -------------------------------------------------------


def test_carregar_ator(usuarios):
    ator = carregar_ator(usuarios["marina"])
    assert (ator.nome, ator.filial_codigo, ator.e_admin) == ("Marina Teste", "F001", False)


def test_carregar_ator_recusa_inativo_ausente_e_tipo_errado(usuarios):
    administracao.desativar_usuario("marina.teste")
    for valor in (usuarios["marina"], 9999, None, "1", True):
        with pytest.raises(ErroAutenticacao):
            carregar_ator(valor)


def test_permissoes(usuarios):
    marina, admin = carregar_ator(usuarios["marina"]), carregar_ator(usuarios["admin"])
    outra = carregar_ator(usuarios["carlos"]).filial_id
    assert permissoes.pode_acessar_filial(marina, marina.filial_id)
    assert not permissoes.pode_acessar_filial(marina, outra)
    assert permissoes.pode_acessar_filial(admin, outra)
    permissoes.exigir_admin(admin)
    with pytest.raises(ErroPermissao):
        permissoes.exigir_admin(marina)


def test_erros_de_dominio():
    e = ErroValidacao("titulo", "Informe o título.")
    assert (e.campo, e.mensagem, str(e)) == ("titulo", "Informe o título.", "Informe o título.")
    for classe in (ErroAutenticacao, ErroPermissao, ErroNaoEncontrado, ErroConflito):
        assert issubclass(classe, ErroDominio)
        assert classe().args == classe().args  # sem detalhe variável
    assert relogio.agora().utcoffset() == timedelta(0)


# --- administração, seed e CLI --------------------------------------------------------


@pytest.mark.parametrize(
    ("campo", "kwargs"),
    [
        ("nome", {"nome": " "}),
        ("nome", {"nome": "n" * 101}),
        ("login", {"login": "ab"}),
        ("login", {"login": "com espaco"}),
        ("login", {"login": "l" * 51}),
        ("senha", {"senha": "curta"}),
        ("senha", {"senha": "s" * 129}),
        ("filial", {"filial_codigo": "F999"}),
    ],
)
def test_criar_usuario_valida_as_entradas(usuarios, campo, kwargs):
    dados = {"nome": "Novo", "login": "novo.usuario", "senha": SENHA, "filial_codigo": "F001"}
    with pytest.raises(ErroValidacao) as info:
        administracao.criar_usuario(**{**dados, **kwargs})
    assert info.value.campo == campo


def test_duplicados_geram_conflito(usuarios):
    with pytest.raises(ErroConflito):
        administracao.criar_filial("f001", "Repetida")
    with pytest.raises(ErroConflito):
        administracao.criar_usuario("Outra", "MARINA.TESTE", SENHA, "F001")


def test_seed_duas_vezes_nao_duplica(banco):
    from osapp.models import CategoriaCusto

    # As categorias já vêm da migração 0004; o seed só completa o que faltar.
    assert seed.executar(SENHA) == {"filiais": 1, "categorias": 0, "usuarios": 1}
    assert seed.executar(SENHA) == {"filiais": 0, "categorias": 0, "usuarios": 0}
    with sessao() as s:
        assert [(f.codigo, f.nome) for f in s.query(Filial)] == [("1007", "Jardinópolis")]
        assert [c.codigo for c in s.query(CategoriaCusto).order_by(CategoriaCusto.ordem)] == [
            "MAO_DE_OBRA",
            "PECAS_MATERIAIS",
            "SERVICOS_TERCEIROS",
            "OUTROS",
        ]
        usuarios = {u.login: (u.filial.codigo, u.e_admin) for u in s.query(Usuario)}
    assert usuarios == {"admin": ("1007", True)}  # sem exemplos por padrão


def test_seed_com_exemplos(banco):
    assert seed.executar(SENHA, exemplos=True)["usuarios"] == 5
    assert seed.executar(SENHA, exemplos=True)["usuarios"] == 0
    with sessao() as s:
        usuarios = {u.login: (u.filial.codigo, u.papel, u.is_gerente) for u in s.query(Usuario)}
    assert usuarios == {
        "admin": ("1007", "admin", False),
        "gerente.norte": ("1007", "manutencao", True),
        "marina.teste": ("1007", "manutencao", False),
        "joao.ficticio": ("1007", "manutencao", False),
        "usuario.teste": ("1007", "usuario", False),  # prompt 19: abre solicitações
    }
    assert autenticar("joao.ficticio", SENHA).nome == "João Fictício"


def test_seed_le_os_seed_exemplos(banco, monkeypatch):
    monkeypatch.setenv("OS_SEED_SENHA", SENHA)
    monkeypatch.delenv("OS_SEED_EXEMPLOS", raising=False)
    assert seed.main() == 0
    with sessao() as s:
        assert [u.login for u in s.query(Usuario)] == ["admin"]
    monkeypatch.setenv("OS_SEED_EXEMPLOS", "1")
    assert seed.main() == 0
    with sessao() as s:
        assert s.query(Usuario).count() == 5


def test_seed_exige_senha_e_nao_a_imprime(banco, monkeypatch, capsys):
    monkeypatch.delenv("OS_SEED_SENHA", raising=False)
    assert seed.main() == 1
    monkeypatch.setenv("OS_SEED_SENHA", "curta")
    assert seed.main() == 1
    monkeypatch.setenv("OS_SEED_SENHA", SENHA)
    assert seed.main() == 0
    saida = capsys.readouterr()
    assert SENHA not in saida.out + saida.err


@pytest.mark.parametrize(
    ("senha", "motivo"),
    [
        (None, "OS_SEED_SENHA não está definida"),
        ("", "OS_SEED_SENHA não está definida"),
        ("Curta-123", "OS_SEED_SENHA tem menos de 10 caracteres"),
    ],
)
def test_seed_pulado_registra_erro_claro(banco, monkeypatch, caplog, senha, motivo):
    """Decisão de 21/11/2026: o seed pulado nunca é silencioso, e o log diz por quê."""
    if senha is None:
        monkeypatch.delenv("OS_SEED_SENHA", raising=False)
    else:
        monkeypatch.setenv("OS_SEED_SENHA", senha)
    with caplog.at_level(logging.ERROR, logger="osapp.seed"):
        assert seed.main() == 1
    erros = [r for r in caplog.records if r.name == "osapp.seed" and r.levelno == logging.ERROR]
    assert len(erros) == 1
    log = erros[0].getMessage()
    assert log.startswith("Seed NÃO executado: ") and motivo in log
    if senha:
        assert senha not in log
    with sessao() as s:
        assert s.query(Usuario).count() == 0


def test_cli(banco, monkeypatch, capsys):
    monkeypatch.setattr(cli.getpass, "getpass", lambda _p="": SENHA)
    assert cli.main(["criar-filial", "--codigo", "F001", "--nome", "Filial Modelo Norte"]) == 0
    assert (
        cli.main(
            [
                "criar-usuario",
                "--nome",
                "Marina Teste",
                "--login",
                "marina.teste",
                "--filial",
                "F001",
            ]
        )
        == 0
    )
    assert (
        cli.main(
            [
                "criar-usuario",
                "--nome",
                "Marina Teste",
                "--login",
                "marina.teste",
                "--filial",
                "F001",
            ]
        )
        == 1
    )  # duplicado
    assert autenticar("marina.teste", SENHA)

    _falhar(5)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _p="": "nova-senha-456")
    assert cli.main(["redefinir-senha", "--login", "marina.teste"]) == 0
    assert autenticar("marina.teste", "nova-senha-456")  # a espera do login foi zerada

    assert cli.main(["desativar-usuario", "--login", "marina.teste"]) == 0
    with pytest.raises(ErroAutenticacao):
        autenticar("marina.teste", "nova-senha-456")
    assert cli.main(["desativar-usuario", "--login", "nao.existe"]) == 1
    saida = capsys.readouterr()
    assert SENHA not in saida.out + saida.err and "nova-senha-456" not in saida.out + saida.err


def test_cli_interativa_e_senhas_diferentes(banco, monkeypatch):
    respostas = iter(["F002", "Filial Modelo Sul"])
    monkeypatch.setattr("builtins.input", lambda _p="": next(respostas))
    assert cli.main(["criar-filial"]) == 0
    senhas_digitadas = iter([SENHA, "diferente-000"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _p="": next(senhas_digitadas))
    assert (
        cli.main(
            [
                "criar-usuario",
                "--nome",
                "Carlos Exemplo",
                "--login",
                "carlos.exemplo",
                "--filial",
                "F002",
            ]
        )
        == 1
    )
    assert _usuario("carlos.exemplo") is None


def test_cli_nao_aceita_senha_por_argumento():
    with pytest.raises(SystemExit):
        cli.criar_parser().parse_args(["criar-usuario", "--senha", "x"])


def test_perfil_gerente_e_definir_perfil(banco, monkeypatch, capsys):
    seed.executar(SENHA, exemplos=True)
    gerente = autenticar("gerente.norte", SENHA)
    assert (gerente.is_gerente, gerente.e_admin) == (True, False)
    assert autenticar("marina.teste", SENHA).is_gerente is False
    assert autenticar("admin", SENHA).is_gerente is False  # administrador prevalece

    administracao.definir_perfil("marina.teste", "gerente")
    assert carregar_ator(_usuario().id).is_gerente is True
    administracao.definir_perfil("marina.teste", "administrador")
    ator = carregar_ator(_usuario().id)
    assert (ator.e_admin, ator.is_gerente) == (True, False)
    administracao.definir_perfil("marina.teste", "usuario")
    ator = carregar_ator(_usuario().id)
    assert (ator.e_admin, ator.is_gerente) == (False, False)

    with pytest.raises(ErroValidacao):
        administracao.definir_perfil("marina.teste", "chefe")
    with pytest.raises(ErroNaoEncontrado):
        administracao.definir_perfil("nao.existe", "gerente")
    with pytest.raises(ErroValidacao):
        administracao.criar_usuario("Duplo", "duplo.perfil", SENHA, "F001", True, True)

    assert cli.main(["definir-perfil", "--login", "joao.ficticio", "--perfil", "gerente"]) == 0
    assert autenticar("joao.ficticio", SENHA).is_gerente is True
    with pytest.raises(SystemExit):  # --admin e --gerente juntos são recusados
        cli.criar_parser().parse_args(["criar-usuario", "--admin", "--gerente"])
