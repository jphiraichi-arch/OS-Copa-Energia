import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from osapp.db import sessao
from osapp.models import OrdemServico, OsEvento
from osapp.services import ordens, relogio, status
from osapp.services.erros import (
    ErroAutenticacao,
    ErroNaoEncontrado,
    ErroPermissao,
    ErroValidacao,
)

T0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


def criar(ator_id, **extras):
    dados = {
        "titulo": "Troca de rolamento",
        "descricao": "Esteira com ruído.",
        "valor_previsto_centavos": 15000,
        "tempo_previsto_minutos": 90,
    }
    dados.update(extras)
    return ordens.criar_os(ator_id, **dados)


def contar(modelo) -> int:
    with sessao() as s:
        return s.scalar(select(func.count()).select_from(modelo))


# --- criar_os -------------------------------------------------------------------------


def test_usuario_comum_cria_os_na_propria_filial(cenario, monkeypatch):
    monkeypatch.setattr(relogio, "agora", lambda: T0)
    d = criar(cenario["marina"], titulo="  Troca de rolamento  ")
    assert d.filial_id == cenario["f1"] and d.filial_codigo == "F001"
    assert d.filial_nome == "Filial Modelo Norte"
    assert d.status == status.ABERTA
    assert re.fullmatch(r"F001-2026-\d{6}", d.numero) and d.numero == "F001-2026-000001"
    assert (d.titulo, d.descricao) == ("Troca de rolamento", "Esteira com ruído.")
    assert (d.valor_previsto_centavos, d.tempo_previsto_minutos) == (15000, 90)
    assert (d.criado_por_id, d.criado_por_nome) == (cenario["marina"], "Marina Teste")
    assert d.criado_em == T0 and d.versao == 1
    assert d.executor_id is None and d.valor_realizado_centavos is None

    eventos = ordens.listar_eventos(cenario["marina"], d.id)
    assert len(eventos) == 1
    e = eventos[0]
    assert (e.tipo, e.campo, e.nome_usuario, e.data_hora) == ("CRIACAO", None, "Marina Teste", T0)
    assert (e.valor_antigo, e.valor_novo) == (None, None)


def test_usuario_comum_pode_informar_a_propria_filial(cenario):
    assert criar(cenario["marina"], filial_id=cenario["f1"]).filial_id == cenario["f1"]


def test_usuario_comum_nao_cria_em_outra_filial(cenario, caplog):
    with pytest.raises(ErroPermissao):
        criar(cenario["marina"], filial_id=cenario["f2"])
    assert contar(OrdemServico) == 0 and contar(OsEvento) == 0
    assert f"usuario_id={cenario['marina']}" in caplog.text  # a recusa é registrada em log


def test_admin_cria_em_qualquer_filial(cenario):
    assert criar(cenario["admin"], filial_id=cenario["f2"]).filial_codigo == "F002"
    assert criar(cenario["admin"]).filial_codigo == "F001"  # None = a filial do admin
    with pytest.raises(ErroValidacao) as info:
        criar(cenario["admin"], filial_id=9999)
    assert info.value.campo == "filial_id"
    assert contar(OrdemServico) == 2


def test_numero_usa_o_ano_no_fuso_da_aplicacao(cenario, monkeypatch):
    monkeypatch.setenv("OS_TZ", "America/Sao_Paulo")
    monkeypatch.setattr(relogio, "agora", lambda: datetime(2027, 1, 1, 1, 0, tzinfo=UTC))
    assert criar(cenario["marina"]).numero == "F001-2026-000001"  # ainda 31/12/2026 às 22h


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("titulo", "ab"),  # curto demais
        ("titulo", "  ab  "),  # curto depois de aparar
        ("titulo", "t" * 121),  # longo demais
        ("titulo", None),
        ("titulo", 123),
        ("descricao", ""),
        ("descricao", "   "),
        ("descricao", "d" * 2001),
        ("descricao", None),
        ("valor_previsto_centavos", -1),
        ("valor_previsto_centavos", 10_000_000_000),
        ("valor_previsto_centavos", 10.5),
        ("valor_previsto_centavos", "100"),
        ("valor_previsto_centavos", True),
        ("valor_previsto_centavos", None),
        ("tempo_previsto_minutos", 0),
        ("tempo_previsto_minutos", -5),
        ("tempo_previsto_minutos", 60_000),
        ("tempo_previsto_minutos", 1.5),
        ("tempo_previsto_minutos", "90"),
        ("tempo_previsto_minutos", False),
        ("filial_id", "1"),
    ],
)
def test_validacao_recusa(cenario, campo, valor):
    with pytest.raises(ErroValidacao) as info:
        criar(cenario["admin"], **{campo: valor})
    assert info.value.campo == campo and info.value.mensagem
    assert contar(OrdemServico) == 0 and contar(OsEvento) == 0


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("titulo", "abc"),
        ("titulo", "t" * 120),
        ("descricao", "d"),
        ("descricao", "d" * 2000),
        ("valor_previsto_centavos", 0),
        ("valor_previsto_centavos", 9_999_999_999),
        ("tempo_previsto_minutos", 1),
        ("tempo_previsto_minutos", 59_999),
    ],
)
def test_validacao_aceita_os_limites(cenario, campo, valor):
    assert getattr(criar(cenario["marina"], **{campo: valor}), campo) == valor


def test_criacoes_em_sequencia_recebem_numeros_diferentes(cenario, monkeypatch):
    monkeypatch.setattr(relogio, "agora", lambda: T0)
    numeros = [criar(cenario["marina"]).numero, criar(cenario["marina"]).numero]
    assert numeros == ["F001-2026-000001", "F001-2026-000002"]
    assert criar(cenario["carlos"]).numero == "F002-2026-000001"  # uma sequência por filial


# Numeração detalhada (contador, ano local, concorrência): tests/test_numeracao.py.


def test_se_o_evento_falha_a_os_nao_e_criada(cenario, monkeypatch):
    def falhar(*_a, **_k):
        raise RuntimeError("falha simulada ao gravar o evento")

    monkeypatch.setattr(ordens, "registrar_evento", falhar)
    with pytest.raises(RuntimeError):
        criar(cenario["marina"])
    assert contar(OrdemServico) == 0 and contar(OsEvento) == 0


# --- obter_os e listar_eventos --------------------------------------------------------


def test_usuario_comum_nao_le_os_de_outra_filial(cenario):
    de_f2 = criar(cenario["carlos"])
    for chamada in (ordens.obter_os, ordens.listar_eventos):
        with pytest.raises(ErroNaoEncontrado) as outra_filial:
            chamada(cenario["marina"], de_f2.id)
        with pytest.raises(ErroNaoEncontrado) as inexistente:
            chamada(cenario["marina"], 9999)
        assert outra_filial.value.args == inexistente.value.args  # indistinguíveis
    assert ordens.obter_os(cenario["carlos"], de_f2.id).id == de_f2.id


def test_colega_da_mesma_filial_le_a_os(cenario):
    d = criar(cenario["marina"])
    visto = ordens.obter_os(cenario["joao"], d.id)
    # Tudo igual, exceto as ações, que dependem de quem olha (prompt 5).
    assert replace(visto, acoes=d.acoes) == d
    assert d.acoes.pode_editar and not visto.acoes.pode_editar
    assert len(ordens.listar_eventos(cenario["joao"], d.id)) == 1


@pytest.mark.parametrize("os_id", [None, "1", 1.0, True])
def test_obter_com_id_de_tipo_errado(cenario, os_id):
    criar(cenario["marina"])
    with pytest.raises(ErroNaoEncontrado):
        ordens.obter_os(cenario["marina"], os_id)


def test_admin_le_qualquer_os_e_lista_todas(cenario):
    a, b = criar(cenario["marina"]), criar(cenario["carlos"])
    assert ordens.obter_os(cenario["admin"], b.id).filial_codigo == "F002"
    assert len(ordens.listar_eventos(cenario["admin"], b.id)) == 1
    assert {i.id for i in ordens.listar_os(cenario["admin"]).itens} == {a.id, b.id}
    so_f2 = ordens.listar_os(cenario["admin"], filial_id=cenario["f2"]).itens
    assert [i.id for i in so_f2] == [b.id]


# --- listar_os ------------------------------------------------------------------------


def test_lista_de_usuario_comum_nunca_tem_outra_filial(cenario):
    minha = criar(cenario["marina"], titulo="Pintura do portão")
    alheia = criar(cenario["carlos"], titulo="Pintura da sala")
    for filtros in (
        {},
        {"busca": alheia.numero},  # o número exato da OS alheia
        {"busca": "Pintura"},
        {"busca": "%"},
        {"status": status.ABERTA},
        {"filial_id": cenario["f1"]},
    ):
        ids = {i.id for i in ordens.listar_os(cenario["marina"], **filtros).itens}
        assert alheia.id not in ids, filtros
    assert [i.id for i in ordens.listar_os(cenario["marina"], busca="pintura").itens] == [minha.id]
    assert ordens.listar_os(cenario["marina"], busca=alheia.numero).itens == ()


def test_usuario_comum_nao_lista_outra_filial(cenario):
    with pytest.raises(ErroPermissao):
        ordens.listar_os(cenario["marina"], filial_id=cenario["f2"])


def test_resumo_filtros_e_ordem(cenario, monkeypatch):
    monkeypatch.setattr(relogio, "agora", lambda: T0)
    antiga = criar(cenario["marina"], titulo="Primeira OS")
    monkeypatch.setattr(relogio, "agora", lambda: T0 + timedelta(hours=1))
    nova = criar(cenario["marina"], titulo="Segunda OS", valor_previsto_centavos=999)
    pagina = ordens.listar_os(cenario["marina"])
    assert [i.id for i in pagina.itens] == [nova.id, antiga.id] and pagina.tem_mais is False
    r = pagina.itens[0]
    assert (r.numero, r.titulo, r.status, r.filial_codigo) == (
        nova.numero,
        "Segunda OS",
        status.ABERTA,
        "F001",
    )
    assert (r.valor_previsto_centavos, r.criado_em) == (999, T0 + timedelta(hours=1))
    assert ordens.listar_os(cenario["marina"], status=status.CONCLUIDA).itens == ()
    assert len(ordens.listar_os(cenario["marina"], busca="  segunda  ").itens) == 1


@pytest.mark.parametrize(
    ("kwargs", "campo"),
    [
        ({"status": "CANCELADA"}, "status"),
        ({"status": 1}, "status"),
        ({"pagina": 0}, "pagina"),
        ({"pagina": "1"}, "pagina"),
        ({"busca": 123}, "busca"),
        ({"filial_id": "1"}, "filial_id"),
    ],
)
def test_listar_valida_os_filtros(cenario, kwargs, campo):
    with pytest.raises(ErroValidacao) as info:
        ordens.listar_os(cenario["admin"], **kwargs)
    assert info.value.campo == campo


def test_busca_e_limitada_a_100_caracteres(cenario):
    criar(cenario["marina"], titulo="x" * 100)
    assert len(ordens.listar_os(cenario["marina"], busca="x" * 100 + "y" * 50).itens) == 1


@pytest.mark.parametrize("texto", ["' OR 1=1 --", "%", "_", "'; DROP TABLE ordens_servico; --"])
def test_busca_trata_caracteres_especiais_como_texto(cenario, texto):
    criar(cenario["marina"], titulo="Troca de rolamento")
    literal = criar(cenario["marina"], titulo="Caso especial", descricao=f"contém {texto} aqui")
    assert [i.id for i in ordens.listar_os(cenario["marina"], busca=texto).itens] == [literal.id]
    assert contar(OrdemServico) == 2


def test_paginacao(cenario):
    for n in range(51):
        criar(cenario["marina"], titulo=f"OS de teste {n:02d}")
    p1 = ordens.listar_os(cenario["marina"])
    assert len(p1.itens) == 50 and p1.tem_mais is True
    p2 = ordens.listar_os(cenario["marina"], pagina=2)
    assert len(p2.itens) == 1 and p2.tem_mais is False
    assert not {i.id for i in p1.itens} & {i.id for i in p2.itens}


# --- listar_filiais e usuário inativo -------------------------------------------------


def test_listar_filiais(cenario):
    assert [f.codigo for f in ordens.listar_filiais(cenario["admin"])] == ["F001", "F002"]
    proprias = ordens.listar_filiais(cenario["carlos"])
    assert [(f.id, f.codigo, f.nome) for f in proprias] == [
        (cenario["f2"], "F002", "Filial Modelo Sul")
    ]


def test_usuario_inativo_e_recusado_em_toda_funcao(cenario):
    d = criar(cenario["marina"])
    inativa = cenario["inativa"]
    chamadas = [
        lambda: criar(inativa),
        lambda: ordens.obter_os(inativa, d.id),
        lambda: ordens.listar_os(inativa),
        lambda: ordens.listar_eventos(inativa, d.id),
        lambda: ordens.listar_filiais(inativa),
    ]
    for chamada in chamadas:
        with pytest.raises(ErroAutenticacao):
            chamada()
    for chamada in (lambda: ordens.listar_os(9999), lambda: ordens.listar_os(None)):
        with pytest.raises(ErroAutenticacao):
            chamada()
    assert contar(OrdemServico) == 1


def test_status_definidos_uma_vez():
    assert status.ROTULOS == {
        "ABERTA": "Aberta",
        "EM_EXECUCAO": "Em execução",
        "CONCLUIDA": "Concluída",
    }
    assert status.rotulo("ABERTA") == "Aberta" and status.rotulo("OUTRO") == "OUTRO"
    assert status.status_conhecido("CONCLUIDA") and not status.status_conhecido("CANCELADA")
