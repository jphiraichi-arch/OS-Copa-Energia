"""Prompt 22: escopo da busca, sugestões de descrição e relatório com filtro de busca.

Os valores esperados do relatório são contas feitas à mão a partir dos dados fixos abaixo,
não com o código testado.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from osapp.services import administracao, custos, ordens, relatorios
from osapp.services.erros import ErroPermissao, ErroValidacao
from osapp.ui.views.relatorio_tempos import linha_resumo_busca
from tests.fabricas import categoria_id, tipo_id
from tests.test_relatorio_tempos import BASE, DIA, SENHA, H, Relogio

M = timedelta(minutes=1)


@pytest.fixture
def tempo(monkeypatch):
    monkeypatch.setenv("OS_TZ", "America/Sao_Paulo")
    return Relogio(monkeypatch)


@pytest.fixture
def p(banco, tempo):
    """Os mesmos papéis do teste do prompt 18: filiais 1007 e 2001."""
    administracao.criar_filial("1007", "Jardinópolis")
    administracao.criar_filial("2001", "Outra Filial")

    def criar(nome, login, filial, papel):
        return administracao.criar_usuario(nome, login, SENHA, filial, papel=papel).id

    return {
        "sol": criar("Sônia", "sonia.sol", "1007", "usuario"),
        "man": criar("Mário", "mario.man", "1007", "manutencao"),
        "admin": criar("Ana", "ana.admin", "1007", "admin"),
        "sol_f2": criar("Paula", "paula.outra", "2001", "usuario"),
        "man_f2": criar("Otto", "otto.outra", "2001", "manutencao"),
    }


FEITO = "Serviço executado"  # descrição neutra dos itens realizados


def solicitacao(p, tempo, minuto, titulo, previstos, urgencia="media", sol="sol", man="man"):
    """Solicitação aberta em BASE + ``minuto`` minutos, com os itens previstos
    ``previstos`` = [(descrição, valor em centavos), ...]."""
    tempo.agora = BASE + minuto * M
    v = ordens.criar_solicitacao(p[sol], titulo, "Sem detalhes.", urgencia)
    d = ordens.obter_os(p[man], v.id)
    d = ordens.editar_os(
        p[man],
        d.id,
        d.versao,
        {"tempo_previsto_minutos": 60, "tipo_id": tipo_id(), "prioridade": "media"},
    )
    for descricao, valor in previstos:
        d = custos.adicionar_item(
            p[man], d.id, d.versao, "PREVISTO", categoria_id(), descricao, Decimal("1"), valor
        )
    return d


def iniciar(p, tempo, d, depois, man="man"):
    tempo.agora = d.aberta_em + depois
    return ordens.iniciar_execucao(p[man], d.id, d.versao)


def concluir(p, tempo, d, depois, realizado, man="man"):
    quando = d.aberta_em + depois
    tempo.agora = quando
    entrada = [custos.ItemEntrada(categoria_id(), FEITO, Decimal("1"), realizado)]
    return ordens.concluir_os(
        p[man], d.id, d.versao, entrada, quando - 2 * H, quando - H, "Feito.", "Pronto."
    )


def ids(ator_id, termo, escopo=ordens.ESCOPO_ITENS, filial_id=None):
    pagina = ordens.listar_os(ator_id, termo, None, filial_id, 1, None, escopo)
    return sorted(i.id for i in pagina.itens)


@pytest.fixture
def base(p, tempo):
    """Ordens da filial 1007 (e uma da 2001) com títulos e itens escolhidos a dedo."""
    o = {}
    o["tres"] = solicitacao(
        p,
        tempo,
        0,
        "Pedido geral",
        [("Balança rodoviária", 100), ("BALANÇA reserva", 100), ("balanca auxiliar", 100)],
    )
    o["titulo"] = solicitacao(p, tempo, 1, "Motor do carrossel", [("Rolamento", 100)])
    o["itens"] = solicitacao(
        p, tempo, 2, "Revisão", [("Motor elétrico", 100), ("Correia do carrossel", 100)]
    )
    o["so_motor"] = solicitacao(p, tempo, 3, "Bomba", [("Motor da bomba", 100)])
    o["curinga"] = solicitacao(p, tempo, 4, "Ajuste", [("Desconto 50%", 100), ("Peça_A", 100)])
    o["parecido"] = solicitacao(p, tempo, 5, "Ajuste", [("Desconto 500", 100), ("PeçaXA", 100)])
    o["outra"] = solicitacao(
        p, tempo, 6, "Balança", [("Balança rodoviária", 100)], sol="sol_f2", man="man_f2"
    )
    return {k: v.id for k, v in o.items()} | {"numeros": {k: v.numero for k, v in o.items()}}


# --- Regras da busca ----------------------------------------------------------------


@pytest.mark.parametrize("termo", ["balanca", "BALANÇA", "Balança", "  balança  "])
def test_acentos_e_maiusculas(p, base, termo):
    for escopo in ordens.ESCOPOS:
        assert ids(p["man"], termo, escopo) == [base["tres"]]


def test_tres_itens_correspondentes_aparecem_uma_vez(p, base):
    pagina = ordens.listar_os(p["man"], "balanca", None, None, 1, None, ordens.ESCOPO_ITENS)
    assert [i.id for i in pagina.itens] == [base["tres"]]


def test_varias_palavras_exigem_todas(p, base):
    assert ids(p["man"], "motor carrossel") == [base["itens"]]
    assert ids(p["man"], "motor carrossel", ordens.ESCOPO_TUDO) == sorted(
        [base["titulo"], base["itens"]]
    )
    assert ids(p["man"], "carrossel motor bomba", ordens.ESCOPO_TUDO) == []


def test_escopo_itens_e_tudo(p, base):
    # 'rolamento' só aparece num item; 'carrossel' na OS "titulo" só aparece no título.
    for escopo in ordens.ESCOPOS:
        assert ids(p["man"], "rolamento", escopo) == [base["titulo"]]
    assert base["titulo"] not in ids(p["man"], "carrossel", ordens.ESCOPO_ITENS)
    assert base["titulo"] in ids(p["man"], "carrossel", ordens.ESCOPO_TUDO)
    assert ids(p["admin"], "revisao", ordens.ESCOPO_ITENS) == []
    assert ids(p["admin"], "revisao", ordens.ESCOPO_TUDO) == [base["itens"]]


def test_usuario_nunca_busca_nos_itens(p, base):
    for escopo in (ordens.ESCOPO_ITENS, ordens.ESCOPO_TUDO, None):
        assert ids(p["sol"], "rolamento", escopo) == []
        assert ids(p["sol"], "balanca", escopo) == []  # só em itens na filial 1007
        # título e descrição continuam valendo para ele
        assert ids(p["sol"], "carrossel", escopo) == [base["titulo"]]


def test_numero_casa_em_qualquer_escopo(p, base):
    numero = base["numeros"]["so_motor"]
    sufixo = numero.split("-", 1)[1]  # só dígitos e traços
    for ator in ("man", "sol"):
        for escopo in ordens.ESCOPOS:
            assert ids(p[ator], sufixo, escopo) == [base["so_motor"]]
            assert ids(p[ator], numero.lower(), escopo) == [base["so_motor"]]  # com 'OS-'


def test_nunca_outra_filial(p, base):
    assert base["outra"] not in ids(p["man"], "balanca", ordens.ESCOPO_TUDO)
    assert ids(p["man_f2"], "balanca", ordens.ESCOPO_TUDO) == [base["outra"]]
    assert ids(p["sol_f2"], "balanca") == [base["outra"]]  # título da própria filial
    assert ids(p["admin"], "balanca", ordens.ESCOPO_ITENS) == sorted([base["tres"], base["outra"]])


def test_curingas_valem_como_caracteres(p, base):
    assert ids(p["man"], "50%") == [base["curinga"]]
    assert ids(p["man"], "%") == [base["curinga"]]
    assert ids(p["man"], "_") == [base["curinga"]]
    assert ids(p["man"], "peca_a") == [base["curinga"]]
    assert ids(p["man"], "500") == [base["parecido"]]


def test_escopo_invalido(p, base):
    with pytest.raises(ErroValidacao):
        ordens.listar_os(p["man"], "x", None, None, 1, None, "titulo")


# --- Sugestões de descrição ---------------------------------------------------------


@pytest.fixture
def descricoes(p, tempo):
    """Usos na 1007: 'Válvula de gás' 3x (duas grafias), 'Valvulado' 1x, 'Válvula
    esfera' 2x; na 2001 'Válvula de gás' 5x e 'Válvula da outra' 1x."""
    solicitacao(p, tempo, 0, "Pedido A", [("Válvula de gás", 1), ("valvula de gas", 1)])
    solicitacao(p, tempo, 1, "Pedido B", [("Válvula de gás", 1), ("Válvula esfera", 1)])
    solicitacao(p, tempo, 2, "Pedido C", [("Valvulado", 1), ("Válvula esfera", 1)])
    solicitacao(
        p,
        tempo,
        3,
        "Pedido D",
        [("Válvula de gás", 1)] * 5 + [("Válvula da outra", 1)],
        sol="sol_f2",
        man="man_f2",
    )


def _filial(p, papel):
    from osapp.services.auth import carregar_ator

    return carregar_ator(p[papel]).filial_id


def test_sugestoes_mais_usadas_primeiro_e_grafia_mais_frequente(p, descricoes):
    f = _filial(p, "man")
    assert custos.sugerir_descricoes(p["man"], f, "valv") == [
        "Válvula de gás",
        "Válvula esfera",
        "Valvulado",
    ]
    assert custos.sugerir_descricoes(p["admin"], f, "VÁLV") == [
        "Válvula de gás",
        "Válvula esfera",
        "Valvulado",
    ]


def test_sugestoes_so_da_filial(p, descricoes):
    f2 = _filial(p, "man_f2")
    assert custos.sugerir_descricoes(p["man_f2"], f2, "valv") == [
        "Válvula de gás",
        "Válvula da outra",
    ]
    assert "Válvula da outra" not in custos.sugerir_descricoes(p["man"], _filial(p, "man"), "valv")
    with pytest.raises(ErroPermissao):  # manutenção de outra filial
        custos.sugerir_descricoes(p["man"], f2, "valv")


def test_sugestoes_termo_curto_e_limite(p, tempo):
    f = _filial(p, "man")
    solicitacao(p, tempo, 0, "Muitas", [(f"Peça {n:02d}", 1) for n in range(25)])
    assert custos.sugerir_descricoes(p["man"], f, "p") == []
    assert custos.sugerir_descricoes(p["man"], f, " é ") == []
    assert len(custos.sugerir_descricoes(p["man"], f, "peca")) == 8
    assert len(custos.sugerir_descricoes(p["man"], f, "peca", limite=50)) == 20
    assert len(custos.sugerir_descricoes(p["man"], f, "peca", limite=3)) == 3


def test_sugestoes_mais_recente_desempata(p, tempo):
    f = _filial(p, "man")
    solicitacao(p, tempo, 0, "Pedido A", [("Bico antigo", 1)])
    solicitacao(p, tempo, 5, "Pedido B", [("Bico novo", 1)])
    assert custos.sugerir_descricoes(p["man"], f, "bico") == ["Bico novo", "Bico antigo"]


def test_sugestoes_recusadas_ao_usuario(p, descricoes):
    with pytest.raises(ErroPermissao):
        custos.sugerir_descricoes(p["sol"], _filial(p, "sol"), "valv")


# --- Relatório com filtro de busca --------------------------------------------------


@pytest.fixture
def rel(p, tempo):
    """Três solicitações com 'balança' nos itens (A com três itens), duas sem.

    A (alta):  resposta 1h, solução 5h; previsto 300 + 300 + 400 = 1000; realizado 1500
    B (alta):  resposta 2h, solução 8h; previsto 2000; realizado 1000
    C (baixa): resposta 4h, sem solução; previsto 3000
    Ventilador, Esteira (media, sem 'balança'): resposta 10h e 20h; uma concluída em 30h.
    """
    a = solicitacao(
        p,
        tempo,
        0,
        "Pedido A",
        [("Balança rodoviária", 300), ("Balança reserva", 300), ("Célula da balança", 400)],
        "alta",
    )
    a = concluir(p, tempo, iniciar(p, tempo, a, 1 * H), 5 * H, 1500)
    b = solicitacao(p, tempo, 1, "Pedido B", [("Balança de piso", 2000)], "alta")
    b = concluir(p, tempo, iniciar(p, tempo, b, 2 * H), 8 * H, 1000)
    c = solicitacao(p, tempo, 2, "Pedido C", [("Calibração balança", 3000)], "baixa")
    c = iniciar(p, tempo, c, 4 * H)
    d = solicitacao(p, tempo, 3, "Ventilador", [("Rolamento", 700)])
    d = concluir(p, tempo, iniciar(p, tempo, d, 10 * H), 30 * H, 900)
    e = solicitacao(p, tempo, 4, "Esteira", [("Correia", 800)])
    iniciar(p, tempo, e, 20 * H)
    # Outra filial, com 'balança': nunca entra no relatório da 1007.
    solicitacao(p, tempo, 5, "Pedido F", [("Balança", 1)], sol="sol_f2", man="man_f2")
    tempo.agora = BASE + 40 * H
    return {"a": a.id, "b": b.id, "c": c.id}


def _relatorio(ator_id, termo=None, escopo=ordens.ESCOPO_ITENS, pagina=1):
    return relatorios.relatorio_tempos(ator_id, DIA, DIA, None, None, termo, escopo, pagina)


def test_relatorio_filtrado_confere_com_contas_a_mao(p, rel):
    r = _relatorio(p["man"], "BALANCA")
    b = r.busca
    assert (b.correspondentes, b.total_periodo, b.percentual) == (3, 5, 60.0)
    assert r.total_no_periodo == 3
    # Resposta: 1h, 2h, 4h -> média 7h/3 = 8400 s; mediana 2h = 7200 s.
    assert (r.resposta.n, r.resposta.media_segundos, r.resposta.mediana_segundos) == (
        3,
        8400,
        7200,
    )
    # Solução: 5h, 8h -> média 6h30 = 23400 s; mediana 23400 s.
    assert (r.solucao.n, r.solucao.media_segundos, r.solucao.mediana_segundos) == (
        2,
        23400,
        23400,
    )
    por = {u.urgencia: u for u in r.por_urgencia}
    assert (por["alta"].resposta.n, por["alta"].resposta.media_segundos) == (2, 5400)
    assert por["alta"].resposta.mediana_segundos == 5400
    assert (por["alta"].solucao.media_segundos, por["alta"].solucao.mediana_segundos) == (
        23400,
        23400,
    )
    assert (por["baixa"].resposta.n, por["baixa"].resposta.media_segundos) == (1, 14400)
    assert por["baixa"].solucao.n == 0
    assert por["media"].resposta.n == 0 and por["emergencial"].resposta.n == 0
    # Custos: previsto 1000 + 2000 + 3000; concluídas A e B: previsto 3000, realizado 2500.
    c = b.custos
    assert c.previsto_total_centavos == 6000
    assert (c.concluidas, c.previsto_concluidas_centavos, c.realizado_concluidas_centavos) == (
        2,
        3000,
        2500,
    )
    assert (c.diferenca_centavos, c.diferenca_percentual) == (-500, -16.67)
    # Lista: mais recente primeiro; realizado só nas concluídas; A aparece uma vez.
    assert [o.os_id for o in b.ordens] == [rel["c"], rel["b"], rel["a"]]
    assert [o.previsto_centavos for o in b.ordens] == [3000, 2000, 1000]
    assert [o.realizado_centavos for o in b.ordens] == [None, 1000, 1500]
    assert [o.urgencia for o in b.ordens] == ["baixa", "alta", "alta"]
    assert (b.pagina, b.total_paginas) == (1, 1)
    assert linha_resumo_busca(b) == '3 de 5 ordens no período (60%) correspondem a "BALANCA"'


def test_relatorio_sem_termo_nao_muda(p, rel):
    r = _relatorio(p["man"])
    assert r.busca is None and r.total_no_periodo == 5
    # Resposta de todas: 1, 2, 4, 10, 20 h -> mediana 4h.
    assert (r.resposta.n, r.resposta.mediana_segundos) == (5, 4 * 3600)


def test_relatorio_escopo_tudo_e_usuario_recusado(p, rel):
    # 'ventilador' é só título: entra com 'Tudo', não com 'Itens'.
    assert _relatorio(p["man"], "ventilador", ordens.ESCOPO_ITENS).busca.correspondentes == 0
    assert _relatorio(p["man"], "ventilador", ordens.ESCOPO_TUDO).busca.correspondentes == 1
    with pytest.raises(ErroPermissao):
        _relatorio(p["sol"], "balanca")


def test_relatorio_sem_correspondencia(p, rel):
    r = _relatorio(p["man"], "inexistente")
    b = r.busca
    assert (b.correspondentes, b.total_periodo, b.percentual) == (0, 5, 0.0)
    assert r.total_no_periodo == 0 and b.ordens == ()
    assert r.resposta.n == 0 and r.resposta.media_segundos is None
    assert b.custos.previsto_total_centavos == 0 and b.custos.diferenca_percentual is None


def test_relatorio_nunca_outra_filial(p, rel):
    r = _relatorio(p["man_f2"], "balanca")
    assert (r.busca.correspondentes, r.busca.total_periodo) == (1, 1)
    admin = relatorios.relatorio_tempos(p["admin"], DIA, DIA, None, None, "balanca")
    assert admin.busca.correspondentes == 4  # todas as filiais


def test_relatorio_paginado_50_por_pagina(p, tempo):
    for n in range(53):
        solicitacao(p, tempo, n, f"Pedido {n}", [("Balança", 10)])
    primeira = _relatorio(p["man"], "balanca")
    assert primeira.busca.correspondentes == 53 and primeira.busca.total_paginas == 2
    assert len(primeira.busca.ordens) == 50
    segunda = _relatorio(p["man"], "balanca", pagina=2)
    assert len(segunda.busca.ordens) == 3
    vistos = [o.os_id for o in primeira.busca.ordens + segunda.busca.ordens]
    assert len(set(vistos)) == 53 and vistos == sorted(vistos, reverse=True)
    with pytest.raises(ErroValidacao):
        _relatorio(p["man"], "balanca", pagina=0)


def test_linha_resumo_sem_total():
    b = relatorios.ResultadoBusca(
        termo="x",
        escopo="itens",
        correspondentes=0,
        total_periodo=0,
        percentual=None,
        custos=None,
        ordens=(),
        pagina=1,
        total_paginas=1,
    )
    assert linha_resumo_busca(b) == '0 de 0 ordens no período correspondem a "x"'


def test_periodo_padrao_ainda_funciona_com_termo(p, rel):
    r = relatorios.relatorio_tempos(p["man"], termo="balanca")
    assert r.data_fim - r.data_inicio == timedelta(days=relatorios.DIAS_PADRAO - 1)
    assert isinstance(r.data_inicio, date)
