"""Prompt 12: itens de custo (quantidade exata), equipamentos, migração 0004, consolidação 1007."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import MetaData, func, inspect, select
from sqlalchemy.exc import IntegrityError, StatementError

from osapp import cli, db
from osapp.db import sessao
from osapp.models import CategoriaCusto, Equipamento, OrdemServico, OsItemCusto, Usuario
from osapp.services import administracao, ordens
from osapp.services.erros import ErroValidacao
from tests.conftest import config_alembic
from tests.fabricas import nova_filial, nova_os, novo_usuario

AGORA = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


@pytest.fixture
def os_base(banco):
    with sessao() as s:
        f = nova_filial(s, "1007", "Jardinópolis")
        u = novo_usuario(s, f)
        o = nova_os(s, f, u)
        categoria = s.scalars(select(CategoriaCusto).where(CategoriaCusto.codigo == "OUTROS")).one()
        return {"os": o.id, "categoria": categoria.id, "filial": f.id}


def item(dados, **extras):
    valores = {
        "os_id": dados["os"],
        "fase": "PREVISTO",
        "categoria_id": dados["categoria"],
        "descricao": "Rolamento",
        "quantidade": Decimal("1.00"),
        "valor_unitario_centavos": 1000,
    }
    valores.update(extras)
    return OsItemCusto(**valores)


# --- Quantidade exata ------------------------------------------------------------------


@pytest.mark.parametrize("texto", ["0.01", "1.50", "99999.99", "1", "12.30"])
def test_quantidade_ida_e_volta_exata(os_base, texto):
    with sessao() as s:
        s.add(item(os_base, quantidade=Decimal(texto)))
    with sessao() as s:
        lida = s.scalars(select(OsItemCusto)).one().quantidade
    assert isinstance(lida, Decimal)
    assert lida == Decimal(texto) and str(lida) == str(Decimal(texto).quantize(Decimal("0.01")))


@pytest.mark.parametrize("valor", [1.5, "1.5", True])
def test_quantidade_recusa_float_e_texto(os_base, valor):
    with pytest.raises(StatementError), sessao() as s:
        s.add(item(os_base, quantidade=valor))


def test_quantidade_recusa_mais_de_duas_casas(os_base):
    with pytest.raises(StatementError), sessao() as s:
        s.add(item(os_base, quantidade=Decimal("1.005")))


@pytest.mark.parametrize(
    "extras",
    [
        {"quantidade": Decimal("0")},
        {"quantidade": Decimal("-1")},
        {"valor_unitario_centavos": -1},
        {"fase": "OUTRA"},
    ],
)
def test_restricoes_do_banco(os_base, extras):
    with pytest.raises(IntegrityError), sessao() as s:
        s.add(item(os_base, **extras))


def test_os_com_itens_nao_pode_ser_apagada(os_base):
    with sessao() as s:
        s.add(item(os_base))
    with pytest.raises(IntegrityError), sessao() as s:
        s.delete(s.get(OrdemServico, os_base["os"]))


def test_equipamento_e_campos_sap(os_base):
    with sessao() as s:
        eq = Equipamento(filial_id=os_base["filial"], nome="Compressor 1", codigo_sap="10002345")
        s.add(eq)
        s.flush()
        o = s.get(OrdemServico, os_base["os"])
        o.equipamento_id, o.numero_sap = eq.id, "4000123"
    with sessao() as s:
        o = s.get(OrdemServico, os_base["os"])
        assert (o.equipamento_id is not None, o.equipamento_outro, o.numero_sap) == (
            True,
            None,
            "4000123",
        )
        assert s.get(Equipamento, o.equipamento_id).ativo is True


# --- Migração 0004 com dados do esquema anterior ---------------------------------------


def test_migracao_0004_preserva_os_dados(banco_vazio):
    cfg = config_alembic()
    command.upgrade(cfg, "0003")
    db.reiniciar()
    engine = db.obter_engine()
    t = MetaData()
    t.reflect(bind=engine)
    with engine.begin() as c:
        c.execute(t.tables["filiais"].insert().values(id=1, codigo="F001", nome="Filial Norte"))
        c.execute(
            t.tables["usuarios"]
            .insert()
            .values(
                id=1, nome="Marina", login="marina", senha_hash="x", filial_id=1, is_gerente=True
            )
        )
        c.execute(
            t.tables["ordens_servico"]
            .insert()
            .values(
                id=1,
                numero="OS-2026-000001",
                filial_id=1,
                criado_por_id=1,
                titulo="Antiga",
                descricao="Antiga.",
                status="CONCLUIDA",
                valor_previsto_centavos=10000,
                valor_realizado_centavos=12000,
                tempo_previsto_minutos=60,
                criado_em=AGORA,
                atualizado_em=AGORA,
                versao=3,
            )
        )
        c.execute(
            t.tables["os_eventos"]
            .insert()
            .values(id=1, os_id=1, usuario_id=1, data_hora=AGORA, tipo="CRIACAO")
        )
    db.reiniciar()

    def ler():
        db.reiniciar()
        e = db.obter_engine()
        m = MetaData()
        m.reflect(bind=e)
        with e.connect() as c:
            os_ = c.execute(select(m.tables["ordens_servico"])).mappings().one()
            return (
                dict(os_),
                c.execute(select(m.tables["usuarios"])).mappings().one()["is_gerente"],
                len(c.execute(select(m.tables["os_eventos"])).all()),
                set(m.tables),
            )

    command.upgrade(cfg, "0004")
    os_, gerente, eventos, tabelas = ler()
    assert {"categorias_custo", "os_itens_custo", "equipamentos", "os_sequencias"} <= tabelas
    assert (os_["numero"], os_["valor_previsto_centavos"], os_["valor_realizado_centavos"]) == (
        "OS-2026-000001",
        10000,
        12000,
    )
    assert (os_["numero_sap"], os_["equipamento_id"], os_["equipamento_outro"]) == (
        None,
        None,
        None,
    )
    assert (os_["versao"], gerente, eventos) == (3, True, 1)
    with db.obter_engine().connect() as c:
        m = MetaData()
        m.reflect(bind=db.obter_engine())
        assert len(c.execute(select(m.tables["categorias_custo"])).all()) == 4

    command.downgrade(cfg, "0003")
    os_, gerente, eventos, tabelas = ler()
    assert "os_itens_custo" not in tabelas and "numero_sap" not in os_
    assert (os_["numero"], os_["valor_realizado_centavos"], gerente, eventos) == (
        "OS-2026-000001",
        12000,
        True,
        1,
    )
    command.upgrade(cfg, "0004")
    assert not [n for n in inspect(db.obter_engine()).get_table_names() if n.startswith("_alembic")]


# --- Consolidação na filial 1007 -------------------------------------------------------


@pytest.fixture
def producao_simulada(banco):
    """Como a produção: F001/F002 e usuários fictícios; depois o seed novo cria a 1007."""
    from osapp import seed

    with sessao() as s:
        f1 = nova_filial(s, "F001", "Filial Modelo Norte")
        f2 = nova_filial(s, "F002", "Filial Modelo Sul")
        admin = novo_usuario(s, f1, "admin", "Administrador", papel="admin")
        novo_usuario(s, f1, "marina.teste", "Marina Teste")
        novo_usuario(s, f2, "carlos.exemplo", "Carlos Exemplo")
        novo_usuario(s, f1, "ana.real", "Ana Real")
        nova_os(s, f1, admin, "OS-2026-000001")
    seed.executar("senha-ficticia-123")


def test_simulacao_nao_altera_nada(producao_simulada):
    plano = administracao.planejar_consolidacao()
    assert plano.filial_destino == "1007 - Jardinópolis"
    assert plano.desativar_usuarios == ("marina.teste", "carlos.exemplo")
    assert plano.mover_usuarios == ("admin", "ana.real")
    assert plano.mover_ordens == ("OS-2026-000001",)
    assert any(
        f.startswith("F001 - Filial Modelo Norte: 3 usuário(s), 1 OS")
        for f in plano.filiais_de_origem
    )
    assert administracao.planejar_consolidacao() == plano  # nada mudou


def test_aplicar_consolidacao(producao_simulada):
    with pytest.raises(ErroValidacao):
        administracao.aplicar_consolidacao("marina.teste")  # não é admin
    administracao.aplicar_consolidacao("admin")
    with sessao() as s:
        usuarios = {u.login: (u.filial.codigo, u.ativo) for u in s.query(Usuario)}
        assert usuarios["marina.teste"][1] is False and usuarios["carlos.exemplo"][1] is False
        assert usuarios["admin"] == ("1007", True) and usuarios["ana.real"] == ("1007", True)
        ordem = s.scalars(select(OrdemServico)).one()
        assert (ordem.numero, ordem.filial.codigo) == ("OS-2026-000001", "1007")  # número mantido
    with sessao() as s:
        aid = s.scalars(select(Usuario.id).where(Usuario.login == "admin")).one()
    evento = ordens.listar_eventos(aid, 1)[-1]
    assert (evento.tipo, evento.campo, evento.valor_antigo, evento.valor_novo) == (
        "EDICAO",
        "filial_id",
        "F001",
        "1007",
    )
    assert administracao.planejar_consolidacao().vazio  # rodar de novo não muda nada


def test_cli_consolidar(producao_simulada, capsys):
    assert cli.main(["consolidar-1007"]) == 0
    saida = capsys.readouterr().out
    assert "SIMULAÇÃO" in saida and "carlos.exemplo" in saida
    assert cli.main(["consolidar-1007", "--aplicar"]) == 1  # sem --responsavel
    assert cli.main(["consolidar-1007", "--aplicar", "--responsavel", "admin"]) == 0
    assert "APLICADO" in capsys.readouterr().out


# --- Migração 0005: o preço único vira itens -------------------------------------------


def test_migracao_0005_mantem_os_totais_e_o_downgrade_os_restaura(banco_vazio):
    cfg = config_alembic()
    command.upgrade(cfg, "0004")
    db.reiniciar()
    engine = db.obter_engine()
    t = MetaData()
    t.reflect(bind=engine)
    eq = None
    with engine.begin() as c:
        c.execute(t.tables["filiais"].insert().values(id=1, codigo="1007", nome="Jardinópolis"))
        c.execute(
            t.tables["usuarios"]
            .insert()
            .values(id=1, nome="Ana", login="ana", senha_hash="x", filial_id=1)
        )
        eq = c.execute(
            t.tables["equipamentos"].insert().values(filial_id=1, nome="Compressor 1")
        ).inserted_primary_key[0]
        base = {
            "filial_id": 1,
            "criado_por_id": 1,
            "titulo": "T",
            "descricao": "D",
            "tempo_previsto_minutos": 60,
            "criado_em": AGORA,
            "atualizado_em": AGORA,
            "versao": 1,
        }
        ordens_ = t.tables["ordens_servico"]
        c.execute(
            ordens_.insert().values(
                id=1, numero="A1", status="ABERTA", valor_previsto_centavos=15000, **base
            )
        )
        c.execute(
            ordens_.insert().values(
                id=2,
                numero="A2",
                status="CONCLUIDA",
                valor_previsto_centavos=10000,
                valor_realizado_centavos=12345,
                **base,
            )
        )
        c.execute(
            ordens_.insert().values(
                id=3,
                numero="A3",
                status="ABERTA",
                valor_previsto_centavos=0,
                equipamento_id=eq,
                **base,
            )
        )
    antes = {1: (15000, None), 2: (10000, 12345), 3: (0, None)}

    def estado():
        db.reiniciar()
        e = db.obter_engine()
        m = MetaData()
        m.reflect(bind=e)
        with e.connect() as c:
            return (
                [
                    dict(r)
                    for r in c.execute(
                        select(m.tables["ordens_servico"]).order_by(m.tables["ordens_servico"].c.id)
                    ).mappings()
                ],
                [dict(r) for r in c.execute(select(m.tables["os_itens_custo"])).mappings()],
            )

    # Lido pelo ORM, que reflete o esquema mais novo: sobe até o head (0006 e 0007 não
    # mexem em itens de custo) e, no downgrade, desce por eles também.
    command.upgrade(cfg, "head")
    linhas, itens_ = estado()
    assert all("valor_previsto_centavos" not in linha for linha in linhas)
    with sessao() as s:
        for os_id, (previsto, realizado) in antes.items():
            ordem = s.get(OrdemServico, os_id)
            totais = {"PREVISTO": 0, "REALIZADO": 0}
            for item in ordem.itens:
                assert (item.descricao, item.quantidade, item.categoria.codigo) == (
                    "Valor total (migrado)",
                    Decimal("1.00"),
                    "OUTROS",
                )
                totais[item.fase] += item.valor_unitario_centavos
            assert totais["PREVISTO"] == previsto
            assert totais["REALIZADO"] == (realizado or 0)
            assert any(i.fase == "REALIZADO" for i in ordem.itens) == (realizado is not None)
    equipamentos = {
        linha["id"]: (linha["equipamento_id"], linha["equipamento_outro"]) for linha in linhas
    }
    assert equipamentos == {1: (None, "Não informado"), 2: (None, "Não informado"), 3: (eq, None)}

    command.downgrade(cfg, "0004")
    linhas, itens_ = estado()
    assert {
        r["id"]: (r["valor_previsto_centavos"], r["valor_realizado_centavos"]) for r in linhas
    } == antes
    assert itens_ == []  # os itens migrados saem; os totais voltam às colunas
    assert all(r["equipamento_outro"] is None for r in linhas)

    command.upgrade(cfg, "head")  # e sobe de novo sem duplicar
    with sessao() as s:
        assert s.scalar(select(func.count()).select_from(OsItemCusto)) == 4


def test_migracao_0005_soma_itens_reais_no_downgrade(banco):
    """Itens criados depois do 0005 também voltam como soma (arredondada) no downgrade."""
    from osapp.services import ordens
    from tests.fabricas import categoria_id

    with sessao() as s:
        f = nova_filial(s, "1007", "Jardinópolis")
        u = novo_usuario(s, f, papel="admin")
        uid = u.id
    from osapp.services.custos import ItemEntrada

    d = ordens.criar_os(
        uid,
        "Titulo",
        "Descrição.",
        [
            ItemEntrada(
                categoria_id("MAO_DE_OBRA"), "Hora", Decimal("1.5"), 3333
            ),  # 49,995 -> 50,00
            ItemEntrada(categoria_id("PECAS_MATERIAIS"), "Peça", Decimal("2"), 1000),
        ],
        60,
        equipamento_outro="Equipamento de teste",
    )
    assert d.resumo_custos.total_previsto_centavos == 7000
    command.downgrade(config_alembic(), "0004")
    db.reiniciar()
    m = MetaData()
    m.reflect(bind=db.obter_engine())
    with db.obter_engine().connect() as c:
        assert (
            c.execute(select(m.tables["ordens_servico"].c.valor_previsto_centavos)).scalar_one()
            == 7000
        )
        assert len(c.execute(select(m.tables["os_itens_custo"])).all()) == 2  # itens reais ficam
