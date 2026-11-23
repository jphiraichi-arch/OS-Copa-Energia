"""Prompt 16: papel, tipos de manutenção, origem/urgência/prioridade e instantes de status."""

from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from sqlalchemy import MetaData, inspect, select
from sqlalchemy.exc import IntegrityError

from osapp import cli, db
from osapp.db import sessao
from osapp.models import OrdemServico, TipoManutencao, Usuario
from osapp.services import administracao
from tests.conftest import config_alembic
from tests.fabricas import nova_filial, nova_os, novo_usuario

T0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
H = timedelta(hours=1)


def _tabelas():
    db.reiniciar()
    tabelas = MetaData()
    tabelas.reflect(bind=db.obter_engine())
    return tabelas


def _linhas(nome: str) -> list[dict]:
    tabelas = _tabelas()
    with db.obter_engine().connect() as conexao:
        tabela = tabelas.tables[nome]
        return [
            dict(linha)
            for linha in conexao.execute(select(tabela).order_by(tabela.c.id)).mappings()
        ]


def _povoar_0006():
    """Esquema 0006 (antes do prompt 16): usuários e uma OS em cada status."""
    tabelas = _tabelas()
    t = tabelas.tables
    with db.obter_engine().begin() as conexao:
        conexao.execute(t["filiais"].insert().values(id=1, codigo="1007", nome="Jardinópolis"))
        for linha in (
            dict(
                id=1,
                nome="Admin Teste",
                login="admin",
                senha_hash="x",
                filial_id=1,
                is_admin=True,  # coluna do esquema antigo (antes da 0008)
            ),
            dict(id=2, nome="Marina Teste", login="marina.teste", senha_hash="x", filial_id=1),
            dict(
                id=3,
                nome="Gabriela Gerente",
                login="gerente.norte",
                senha_hash="x",
                filial_id=1,
                is_gerente=True,
            ),
        ):
            conexao.execute(t["usuarios"].insert().values(**linha))
        base = dict(
            filial_id=1,
            criado_por_id=2,
            titulo="Teste",
            descricao="Teste.",
            tempo_previsto_minutos=60,
            atualizado_em=T0,
            versao=1,
        )
        for linha in (
            dict(base, id=1, numero="1007-2026-000001", status="ABERTA", criado_em=T0),
            dict(
                base,
                id=2,
                numero="1007-2026-000002",
                status="EM_EXECUCAO",
                criado_em=T0,
                executor_id=2,
                iniciado_em=T0 + H,
            ),
            dict(
                base,
                id=3,
                numero="1007-2026-000003",
                status="CONCLUIDA",
                criado_em=T0,
                executor_id=2,
                iniciado_em=T0 + H,
                concluido_por_id=2,
                concluido_em=T0 + 3 * H,
                inicio_realizado=T0 + H,
                fim_realizado=T0 + 2 * H,
                descricao_realizado="Feito.",
            ),
        ):
            conexao.execute(t["ordens_servico"].insert().values(**linha))
    db.reiniciar()


def test_migracao_0007_com_dados_ida_e_volta(banco_vazio):
    cfg = config_alembic()
    command.upgrade(cfg, "0006")
    _povoar_0006()
    usuarios_antes, ordens_antes = _linhas("usuarios"), _linhas("ordens_servico")

    command.upgrade(cfg, "0007")
    usuarios = {u["login"]: u for u in _linhas("usuarios")}
    assert {login: u["papel"] for login, u in usuarios.items()} == {
        "admin": "admin",
        "marina.teste": "manutencao",
        "gerente.norte": "manutencao",
    }
    coluna = "is_admin"  # esquema antigo (antes da 0008)
    assert all((u["papel"] == "admin") == u[coluna] for u in usuarios.values())
    for ordem in _linhas("ordens_servico"):
        assert ordem["origem"] == "manutencao"
        assert ordem["aberta_em"].replace(tzinfo=UTC) == T0  # = criado_em
        for nova, antiga in (
            ("inicio_execucao_em", "iniciado_em"),
            ("concluida_em", "concluido_em"),
        ):
            assert ordem[nova] == ordem[antiga]  # cópia exata (inclusive None)
        assert ordem["urgencia"] is ordem["prioridade"] is ordem["cancelada_em"] is None
    assert [t["codigo"] for t in _linhas("tipos_manutencao")] == [
        "CORRETIVA",
        "PREVENTIVA",
        "PREDITIVA",
        "MELHORIA",
        "OUTRO",
    ]

    command.downgrade(cfg, "0006")
    assert _linhas("usuarios") == usuarios_antes
    assert _linhas("ordens_servico") == ordens_antes
    assert "tipos_manutencao" not in inspect(db.obter_engine()).get_table_names()

    command.upgrade(cfg, "head")  # sobe de novo sem erro
    assert len(_linhas("tipos_manutencao")) == 5


def test_migracao_para_se_houver_linha_do_tempo_impossivel(banco_vazio):
    cfg = config_alembic()
    command.upgrade(cfg, "0006")
    _povoar_0006()
    with db.obter_engine().begin() as conexao:
        t = _tabelas().tables["ordens_servico"]
        conexao.execute(t.update().where(t.c.id == 2).values(iniciado_em=T0 - H))
    db.reiniciar()
    with pytest.raises(RuntimeError, match="inicio_apos_abertura: 1007-2026-000002"):
        command.upgrade(cfg, "0007")
    db.reiniciar()
    if db.obter_engine().dialect.name == "postgresql":  # DDL transacional: nada mudou
        colunas = {c["name"] for c in inspect(db.obter_engine()).get_columns("usuarios")}
        assert "papel" not in colunas


# --- CHECKs (esquema novo, pelo ORM) -------------------------------------------------


def _ordem_valida(s, **extras):
    filial = nova_filial(s)
    return nova_os(s, filial, novo_usuario(s, filial), aberta_em=T0, **extras)


@pytest.mark.parametrize(
    "extras",
    [
        {"origem": "outra"},
        {"urgencia": "urgente"},
        {"prioridade": "maxima"},
        {"inicio_execucao_em": T0 - H},
        {"inicio_execucao_em": T0 + 2 * H, "concluida_em": T0 + H},
        {"cancelada_em": T0 - H},
        {"inicio_execucao_em": T0 + H, "concluida_em": T0 + 2 * H, "cancelada_em": T0 + 2 * H},
    ],
)
def test_check_recusa_linha_impossivel(banco, extras):
    with pytest.raises(IntegrityError), sessao() as s:
        _ordem_valida(s, **extras)


def test_check_aceita_linha_valida_e_tempo_vazio(banco):
    with sessao() as s:
        ordem = _ordem_valida(
            s,
            origem="solicitacao",
            urgencia="emergencial",
            prioridade="alta",
            inicio_execucao_em=T0 + H,
            concluida_em=T0 + 2 * H,
            tempo_previsto_minutos=None,
            tipo_id=s.scalars(select(TipoManutencao.id)).first(),
        )
        assert ordem.id


def test_check_de_papel(banco):
    with pytest.raises(IntegrityError), sessao() as s:
        novo_usuario(s, nova_filial(s), papel="chefe")


def test_aberta_em_tem_padrao_no_banco(banco):
    """O código implantado não conhece aberta_em: o banco precisa preencher sozinho."""
    with sessao() as s:
        filial = nova_filial(s)
        usuario = novo_usuario(s, filial)
        fid, uid = filial.id, usuario.id
    tabela = _tabelas().tables["ordens_servico"]
    with db.obter_engine().begin() as conexao:
        conexao.execute(
            tabela.insert().values(
                numero="X-1",
                filial_id=fid,
                criado_por_id=uid,
                titulo="T",
                descricao="D",
                status="ABERTA",
                tempo_previsto_minutos=10,
                criado_em=T0,
                atualizado_em=T0,
                versao=1,
            )
        )
    with sessao() as s:
        ordem = s.scalars(select(OrdemServico).where(OrdemServico.numero == "X-1")).one()
        assert ordem.aberta_em is not None and ordem.origem == "manutencao"


# --- previa-papeis e definir-papel ---------------------------------------------------


def _foto():
    return {nome: _linhas(nome) for nome in ("usuarios", "ordens_servico")}


def test_previa_papeis_nao_altera_nada(banco_vazio, capsys):
    """Desde a 0008 a prévia lê o papel atual (antes da 0007: código do prompt 16)."""
    revisao = "head"
    cfg = config_alembic()
    command.upgrade(cfg, "0006")
    _povoar_0006()
    command.upgrade(cfg, revisao)
    antes = _foto()
    assert cli.main(["previa-papeis"]) == 0
    saida = capsys.readouterr().out
    assert _foto() == antes
    linhas = {linha.split()[0]: linha.split() for linha in saida.splitlines()[1:-1]}
    assert linhas["admin"][-2:] == ["sim", "admin"]
    assert linhas["marina.teste"][-2:] == ["não", "manutencao"]
    assert "3 usuário(s). Nada foi alterado." in saida


def test_definir_papel_mantem_e_admin_coerente(banco, capsys):
    administracao.criar_filial("1007", "Jardinópolis")
    administracao.criar_usuario("Admin", "admin", "senha-ficticia-123", "1007", True)
    administracao.criar_usuario("Marina", "marina.teste", "senha-ficticia-123", "1007")

    def estado(login):
        with sessao() as s:
            u = s.scalars(select(Usuario).where(Usuario.login == login)).one()
            return u.papel, u.e_admin

    assert estado("admin") == ("admin", True)
    assert estado("marina.teste") == ("manutencao", False)
    assert cli.main(["definir-papel", "marina.teste", "usuario"]) == 0
    assert estado("marina.teste") == ("usuario", False)
    assert cli.main(["definir-papel", "marina.teste", "admin"]) == 0
    assert estado("marina.teste") == ("admin", True)
    administracao.definir_perfil("marina.teste", "usuario")  # caminho antigo também
    assert estado("marina.teste") == ("manutencao", False)
    with pytest.raises(SystemExit):
        cli.main(["definir-papel", "marina.teste", "chefe"])
