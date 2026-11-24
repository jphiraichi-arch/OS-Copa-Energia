from datetime import UTC, datetime, timedelta

import pytest

from osapp.db import sessao
from osapp.models import OsEvento
from osapp.repositories import FilialRepo, OrdemServicoRepo, OsEventoRepo, UsuarioRepo
from tests.fabricas import nova_filial, nova_os, novo_usuario

BASE = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def dados(banco):
    """Duas filiais e quatro OS. Devolve os ids."""
    with sessao() as s:
        f1 = nova_filial(s, "F001", "Filial Modelo Norte")
        f2 = nova_filial(s, "F002", "Filial Modelo Sul")
        u1 = novo_usuario(s, f1, "marina.teste", "Marina Teste")
        u2 = novo_usuario(s, f2, "carlos.exemplo", "Carlos Exemplo")
        nova_os(
            s,
            f1,
            u1,
            "OS-2026-000001",
            titulo="Troca de rolamento",
            descricao="Esteira com ruído.",
            criado_em=BASE,
        )
        nova_os(
            s,
            f1,
            u1,
            "OS-2026-000002",
            titulo="Pintura do portão",
            descricao="Desconto de 100% negado.",
            status="EM_EXECUCAO",
            criado_em=BASE + timedelta(hours=1),
        )
        nova_os(
            s,
            f2,
            u2,
            "OS-2026-000003",
            titulo="Reparo da BALANÇA",
            descricao="Ajuste do sensor_a.",
            criado_em=BASE + timedelta(hours=2),
        )
        nova_os(
            s,
            f2,
            u2,
            "OS-2026-000004",
            titulo="Vazamento",
            descricao="Rolamento gasto.",
            status="CONCLUIDA",
            criado_em=BASE + timedelta(hours=3),
        )
        return {"f1": f1.id, "f2": f2.id, "u1": u1.id, "u2": u2.id}


def _numeros(busca=None, **filtros) -> list[str]:
    """A busca chega ao repositório como condição pronta (prompt 22): escopo 'tudo'."""
    from types import SimpleNamespace

    from osapp.services import ordens

    condicao = ordens.condicao_busca(busca, ordens.ESCOPO_TUDO, SimpleNamespace(e_usuario=False))
    with sessao() as s:
        return [o.numero for o in OrdemServicoRepo(s).listar(condicao=condicao, **filtros)]


def test_filial_repo(dados):
    with sessao() as s:
        repo = FilialRepo(s)
        assert repo.obter(dados["f1"]).codigo == "F001"
        assert repo.obter(9999) is None
        assert repo.obter_por_codigo("F002").id == dados["f2"]
        assert repo.obter_por_codigo("F999") is None
        assert [f.codigo for f in repo.listar()] == ["F001", "F002"]


def test_usuario_repo(dados):
    with sessao() as s:
        repo = UsuarioRepo(s)
        assert repo.obter(dados["u1"]).login == "marina.teste"
        assert repo.obter(9999) is None
        assert repo.obter_por_login("MARINA.teste").id == dados["u1"]
        assert repo.obter_por_login("ninguem") is None


def test_listar_ordena_da_mais_nova_para_a_mais_antiga(dados):
    assert _numeros() == [
        "OS-2026-000004",
        "OS-2026-000003",
        "OS-2026-000002",
        "OS-2026-000001",
    ]


def test_listar_por_filial(dados):
    assert _numeros(filial_id=dados["f1"]) == ["OS-2026-000002", "OS-2026-000001"]
    assert _numeros(filial_id=9999) == []


def test_listar_por_status(dados):
    assert _numeros(status="ABERTA") == ["OS-2026-000003", "OS-2026-000001"]
    assert _numeros(status="CONCLUIDA", filial_id=dados["f1"]) == []


def test_listar_por_busca(dados):
    assert _numeros(busca="ROLAMENTO") == ["OS-2026-000004", "OS-2026-000001"]  # título e descrição
    assert _numeros(busca="balança") == ["OS-2026-000003"]
    assert _numeros(busca="os-2026-000002") == ["OS-2026-000002"]  # número
    assert _numeros(busca="rolamento", filial_id=dados["f1"]) == ["OS-2026-000001"]
    assert _numeros(busca="inexistente") == []


def test_busca_trata_curingas_como_texto(dados):
    assert _numeros(busca="%") == ["OS-2026-000002"]  # só a que contém '%'
    assert _numeros(busca="_") == ["OS-2026-000003"]  # só a que contém '_'
    assert _numeros(busca="100%") == ["OS-2026-000002"]
    assert _numeros(busca="%%") == []
    assert _numeros(busca="' OR 1=1 --") == []


def test_listar_limite_e_deslocamento(dados):
    assert _numeros(limite=2) == ["OS-2026-000004", "OS-2026-000003"]
    assert _numeros(limite=2, deslocamento=2) == ["OS-2026-000002", "OS-2026-000001"]
    assert _numeros(limite=2, deslocamento=4) == []


def test_ordem_servico_obter(dados):
    with sessao() as s:
        repo = OrdemServicoRepo(s)
        assert repo.obter(1).numero == "OS-2026-000001"
        assert repo.obter(9999) is None


def test_proximo_numero(dados):
    with sessao() as s:
        repo = OrdemServicoRepo(s)
        assert repo.proximo_numero(2026) == "OS-2026-000005"
        assert repo.proximo_numero(2027) == "OS-2027-000001"  # uma sequência por ano


def test_proximo_numero_passa_de_999999(banco):
    with sessao() as s:
        f = nova_filial(s)
        u = novo_usuario(s, f)
        nova_os(s, f, u, "OS-2026-999999")
        assert OrdemServicoRepo(s).proximo_numero(2026) == "OS-2026-1000000"
        nova_os(s, f, u, "OS-2026-1000000")
        assert OrdemServicoRepo(s).proximo_numero(2026) == "OS-2026-1000001"


def test_eventos_adicionar_e_listar_por_os(dados):
    with sessao() as s:
        repo = OsEventoRepo(s)
        repo.adicionar(
            OsEvento(
                os_id=1,
                usuario_id=dados["u1"],
                tipo="STATUS",
                campo="status",
                valor_antigo="ABERTA",
                valor_novo="EM_EXECUCAO",
                data_hora=BASE + timedelta(minutes=5),
            )
        )
        repo.adicionar(OsEvento(os_id=1, usuario_id=dados["u1"], tipo="CRIACAO", data_hora=BASE))
        repo.adicionar(OsEvento(os_id=2, usuario_id=dados["u1"], tipo="CRIACAO", data_hora=BASE))
    with sessao() as s:
        eventos = OsEventoRepo(s).listar_por_os(1)
        assert [e.tipo for e in eventos] == ["CRIACAO", "STATUS"]  # do mais antigo ao mais novo
        assert eventos[1].valor_novo == "EM_EXECUCAO"
        assert OsEventoRepo(s).listar_por_os(9999) == []


def test_os_evento_repo_e_somente_insercao():
    publicos = {n for n in vars(OsEventoRepo) if not n.startswith("_")}
    assert publicos == {"adicionar", "listar_por_os"}
    proibidos = ("atualiz", "alter", "edit", "exclu", "remov", "apag", "delet", "updat")
    assert not [n for n in dir(OsEventoRepo) if any(p in n.lower() for p in proibidos)]
