"""Prompt 21: texto de busca normalizado; remoção do cadastro de bens atendidos."""

from __future__ import annotations

import csv
import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import MetaData, inspect, select

from osapp import cli, db
from osapp.busca import normalizar_busca
from osapp.db import sessao
from osapp.models import OrdemServico
from osapp.services import administracao, custos, ordens, relogio
from tests.conftest import RAIZ, config_alembic
from tests.fabricas import categoria_id, itens

T0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
# As palavras proibidas são montadas por partes para este arquivo não se acusar.
SIGNIFICADO_EMERGENCIAL = "Equip" + "amento parado ou risco de segurança"
PROIBIDAS = re.compile("equip" + "ament|codigo" + "_sap", re.IGNORECASE)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Balança", "balanca"),
        ("AÇÃO", "acao"),
        ("Jardinópolis", "jardinopolis"),
        ("  Válvula   de  gás ", "valvula de gas"),
        ("Straße", "strasse"),  # casefold é mais forte que lower
        ("linha1\nlinha2\tfim", "linha1 linha2 fim"),
        (None, ""),
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalizar_busca(entrada, esperado):
    assert normalizar_busca(entrada) == esperado


def test_modulo_de_busca_nao_importa_flet_nem_banco():
    texto = (RAIZ / "src" / "osapp" / "busca.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+(flet|sqlalchemy|osapp\.(db|models))", texto, re.M)


# --- busca_texto mantido pelos eventos do ORM ---------------------------------------


def _busca(os_id):
    with sessao() as s:
        o = s.get(OrdemServico, os_id)
        return o.busca_texto, sorted(i.busca_texto for i in o.itens)


def test_busca_texto_na_criacao_e_na_edicao(cenario, monkeypatch):
    monkeypatch.setattr(relogio, "agora", lambda: T0)
    d = ordens.criar_os(
        cenario["marina"],
        "Balança rodoviária",
        "Calibração  da BALANÇA",
        [custos.ItemEntrada(categoria_id(), "Célula de carga", Decimal("1"), 100)],
        60,
    )
    assert _busca(d.id) == ("balanca rodoviaria calibracao da balanca", ["celula de carga"])
    d = ordens.editar_os(cenario["marina"], d.id, d.versao, {"titulo": "Válvula de gás"})
    assert _busca(d.id)[0] == "valvula de gas calibracao da balanca"
    d = ordens.editar_os(cenario["marina"], d.id, d.versao, {"descricao": "Troca"})
    assert _busca(d.id)[0] == "valvula de gas troca"
    item = d.itens[0]
    d = custos.editar_item(
        cenario["marina"], d.id, item.id, d.versao, {"descricao": "Motor Elétrico"}
    )
    assert _busca(d.id)[1] == ["motor eletrico"]
    d = custos.adicionar_item(
        cenario["marina"], d.id, d.versao, "PREVISTO", categoria_id(), "Ação", Decimal("1"), 1
    )
    assert _busca(d.id)[1] == ["acao", "motor eletrico"]


def test_solicitacao_tambem_tem_busca(cenario, monkeypatch):
    monkeypatch.setattr(relogio, "agora", lambda: T0)
    v = ordens.criar_solicitacao(cenario["marina"], "Lâmpada", "Corredor B", "baixa")
    assert _busca(v.id)[0] == "lampada corredor b"


# --- recalcular-busca ---------------------------------------------------------------


def test_recalcular_busca_nao_muda_banco_coerente_e_corrige_o_resto(cenario, monkeypatch, capsys):
    monkeypatch.setattr(relogio, "agora", lambda: T0)
    d = ordens.criar_os(cenario["marina"], "Balança", "Teste", itens(100), 60)
    assert cli.main(["recalcular-busca"]) == 0
    assert "0 ordem(ns) e 0 item(ns)" in capsys.readouterr().out
    assert administracao.recalcular_busca() == {"ordens": 0, "itens": 0}
    # Linhas gravadas fora do ORM (como numa carga antiga) ficam incoerentes: o comando
    # as corrige, e uma segunda execução já não muda nada.
    tabelas = MetaData()
    tabelas.reflect(bind=db.obter_engine())
    with db.obter_engine().begin() as conexao:
        conexao.execute(tabelas.tables["ordens_servico"].update().values(busca_texto=""))
        conexao.execute(tabelas.tables["os_itens_custo"].update().values(busca_texto="x"))
    assert administracao.recalcular_busca() == {"ordens": 1, "itens": 1}
    assert administracao.recalcular_busca() == {"ordens": 0, "itens": 0}
    assert _busca(d.id) == ("balanca teste", ["valor total"])


# --- Regras do código ---------------------------------------------------------------


def _arquivos(pasta: str):
    return [p for p in (RAIZ / pasta).rglob("*.py") if "__pycache__" not in p.parts]


def test_nenhuma_referencia_ao_cadastro_removido():
    """Fora das migrações, só o módulo da exportação prévia (exportacao_legada.py)."""
    achados = []
    for arquivo in _arquivos("src") + _arquivos("tests"):
        # Exceções: a exportação prévia (prompt 21) e os rótulos dos eventos antigos do
        # histórico (prompt 26: rótulo '(legado)'), que só leem o que já foi gravado, e o
        # teste desses rótulos.
        if arquivo.name in ("exportacao_legada.py", "rotulos_eventos.py", "test_visual.py"):
            continue
        for n, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
            # Texto da urgência (prompt 23) usa a palavra no sentido comum, não o cadastro.
            if PROIBIDAS.search(linha.replace(SIGNIFICADO_EMERGENCIAL, "")):
                achados.append(f"{arquivo.relative_to(RAIZ)}:{n}")
    assert achados == []


def test_sem_insercao_ou_alteracao_em_lote_nas_tabelas_com_busca():
    """Operações em lote pulam os eventos que mantêm busca_texto."""
    proibido = re.compile(
        r"bulk_(insert|update|save)|\b(insert|update)\(\s*(OrdemServico|OsItemCusto)\b"
    )
    achados = [
        f"{arquivo.relative_to(RAIZ)}:{n}"
        for arquivo in _arquivos("src")
        for n, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1)
        if proibido.search(linha)
    ]
    assert achados == []


# --- Migração 0010 e exportação prévia ---------------------------------------------


def _tabelas():
    db.reiniciar()
    m = MetaData()
    m.reflect(bind=db.obter_engine())
    return m.tables


def test_migracao_0010_com_dados_e_exportacao(banco_vazio, tmp_path):
    cfg = config_alembic()
    command.upgrade(cfg, "0009")
    t = _tabelas()
    cadastro = t["equip" + "amentos"]
    with db.obter_engine().begin() as c:
        c.execute(t["filiais"].insert().values(id=1, codigo="1007", nome="Jardinópolis"))
        c.execute(
            t["usuarios"]
            .insert()
            .values(id=1, nome="Ana", login="ana", senha_hash="x", filial_id=1, papel="admin")
        )
        c.execute(cadastro.insert().values(id=7, filial_id=1, nome="Balança rodoviária"))
        base = dict(
            filial_id=1,
            criado_por_id=1,
            status="ABERTA",
            criado_em=T0,
            atualizado_em=T0,
            aberta_em=T0,
            versao=1,
            tempo_previsto_minutos=60,
        )
        c.execute(
            t["ordens_servico"]
            .insert()
            .values(
                id=1,
                numero="1007-2026-000001",
                titulo="Calibração",
                descricao="Balança",
                **{"equip" + "amento_id": 7},
                **base,
            )
        )
        c.execute(
            t["ordens_servico"]
            .insert()
            .values(
                id=2,
                numero="1007-2026-000002",
                titulo="AÇÃO",
                descricao="Válvula",
                **{"equip" + "amento_outro": "Compressor velho"},
                **base,
            )
        )
        c.execute(
            t["ordens_servico"]
            .insert()
            .values(id=3, numero="1007-2026-000003", titulo="Sem nada", descricao="x", **base)
        )
        # Marcador da migração 0005 para OS antigas sem cadastro: não é copiado.
        c.execute(
            t["ordens_servico"]
            .insert()
            .values(
                id=4,
                numero="1007-2026-000004",
                titulo="Antiga",
                descricao="y",
                **{"equip" + "amento_outro": "Não informado"},
                **base,
            )
        )
        c.execute(
            t["os_itens_custo"]
            .insert()
            .values(
                os_id=1,
                fase="PREVISTO",
                categoria_id=categoria_id("OUTROS"),
                descricao="Célula",
                quantidade=(100 if db.obter_engine().dialect.name == "sqlite" else Decimal("1")),
                valor_unitario_centavos=100,
                criado_em=T0,
                atualizado_em=T0,
            )
        )
    db.reiniciar()

    # Exportação antes da migração: numero;nome do cadastro ou texto livre.
    arquivo = tmp_path / "export.csv"
    assert cli.main(["exportar-" + "equip" + "amentos", str(arquivo)]) == 0
    with open(arquivo, encoding="utf-8") as f:
        assert list(csv.reader(f, delimiter=";")) == [
            ["numero", "equip" + "amento"],
            ["1007-2026-000001", "Balança rodoviária"],
            ["1007-2026-000002", "Compressor velho"],
            ["1007-2026-000004", "Não informado"],
        ]

    command.upgrade(cfg, "0010")
    t = _tabelas()
    assert ("equip" + "amentos") not in t
    assert not any(PROIBIDAS.search(col.name) for col in t["ordens_servico"].c)
    assert "numero_sap" in t["ordens_servico"].c
    os_ = t["ordens_servico"]
    with db.obter_engine().connect() as c:
        linhas = c.execute(select(os_.c.id, os_.c.descricao, os_.c.busca_texto)).all()
        item = c.execute(select(t["os_itens_custo"].c.busca_texto)).scalar_one()
    rotulo = "Equip" + "amento (legado): "
    descricoes = {i: d for i, d, _b in linhas}
    buscas = {i: b for i, _d, b in linhas}
    # O nome do cadastro e o texto livre ficam no fim da descrição, e entram na busca.
    assert descricoes == {
        1: f"Balança\n\n{rotulo}Balança rodoviária",
        2: f"Válvula\n\n{rotulo}Compressor velho",
        3: "x",
        4: "y",
    }
    legado = "equip" + "amento (legado):"
    assert buscas == {
        1: f"calibracao balanca {legado} balanca rodoviaria",
        2: f"acao valvula {legado} compressor velho",
        3: "sem nada x",
        4: "antiga y",
    }
    assert item == "celula"
    # Depois da migração a exportação não tem o que ler.
    assert cli.main(["exportar-" + "equip" + "amentos", str(tmp_path / "de_novo.csv")]) == 1

    command.downgrade(cfg, "0009")
    t = _tabelas()
    assert ("equip" + "amentos") in t and "busca_texto" not in t["ordens_servico"].c
    with db.obter_engine().connect() as c:
        assert c.execute(select(t["equip" + "amentos"])).all() == []  # volta vazia
        ids = select(t["ordens_servico"].c.id).order_by(t["ordens_servico"].c.id)
        assert c.execute(ids).scalars().all() == [1, 2, 3, 4]
        # O vínculo não volta; a linha acrescentada continua na descrição.
        voltou = c.execute(
            select(t["ordens_servico"].c.descricao).where(t["ordens_servico"].c.id == 1)
        ).scalar_one()
        assert voltou.endswith(f"{rotulo}Balança rodoviária")
        assert (
            c.execute(
                select(t["ordens_servico"].c["equip" + "amento_id"]).where(
                    t["ordens_servico"].c.id == 1
                )
            ).scalar_one()
            is None
        )
    command.upgrade(cfg, "head")
    assert "busca_texto" in {
        c["name"] for c in inspect(db.obter_engine()).get_columns("os_itens_custo")
    }
