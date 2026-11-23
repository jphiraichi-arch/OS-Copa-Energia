from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from osapp.db import sessao
from osapp.models import OrdemServico, OsEvento
from osapp.services import ordens, relogio, status
from osapp.services.erros import (
    ErroAutenticacao,
    ErroConflito,
    ErroNaoEncontrado,
    ErroPermissao,
    ErroValidacao,
)
from tests.fabricas import args_de_conclusao, args_de_criacao

T0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
INICIO = T0 - timedelta(hours=3)
FIM = T0 - timedelta(hours=1, minutes=30)  # 90 minutos depois do início


@pytest.fixture(autouse=True)
def relogio_fixo(monkeypatch):
    monkeypatch.setattr(relogio, "agora", lambda: T0)


def criar(ator_id, **extras):
    dados = {
        "titulo": "Troca de rolamento",
        "descricao": "Esteira com ruído.",
        "valor_previsto_centavos": 10000,
        "tempo_previsto_minutos": 60,
    }
    dados.update(extras)
    return ordens.criar_os(ator_id, **args_de_criacao(dados))


def concluir(ator_id, d, **extras):
    dados = {
        "valor_realizado_centavos": 12000,
        "inicio_realizado": INICIO,
        "fim_realizado": FIM,
        "descricao_realizado": "Rolamento trocado.",
    }
    dados.update(extras)
    return ordens.concluir_os(ator_id, d.id, d.versao, **args_de_conclusao(dados))


def preparar(cenario, destino, **extras):
    """OS criada por marina; se preciso, iniciada e concluída por pedro."""
    d = criar(cenario["marina"], **extras)
    if destino in (status.EM_EXECUCAO, status.CONCLUIDA):
        d = ordens.iniciar_execucao(cenario["pedro"], d.id, d.versao)
    if destino == status.CONCLUIDA:
        d = concluir(cenario["pedro"], d)
    if destino == status.CANCELADA:
        d = ordens.cancelar(cenario["admin"], d.id, d.versao)
    assert d.status == destino
    return d


def eventos(cenario, os_id):
    return [
        (e.tipo, e.campo, e.valor_antigo, e.valor_novo)
        for e in ordens.listar_eventos(cenario["admin"], os_id)
    ]


def estado_bruto(os_id):
    with sessao() as s:
        o = s.get(OrdemServico, os_id)
        n_eventos = s.scalar(
            select(func.count()).select_from(OsEvento).where(OsEvento.os_id == os_id)
        )
        return (
            o.status,
            o.versao,
            o.titulo,
            o.executor_id,
            o.filial_id,
            tuple((i.fase, i.valor_unitario_centavos) for i in o.itens),
            n_eventos,
        )


# --- Matriz de permissões: ator x ação x status ---------------------------------------

ATORES = ["marina", "joao", "pedro", "carlos", "admin", "inativa"]
#          criadora  colega  executor  outra filial  admin  inativa
OK, PERM, NAOENC, AUT = "ok", ErroPermissao, ErroNaoEncontrado, ErroAutenticacao

MATRIZ = {
    # (ação, status): resultado esperado para cada ator, na ordem de ATORES
    # Prompt 17: editar_os é da manutenção da filial (os três são 'manutencao').
    ("editar", status.ABERTA): [OK, OK, OK, NAOENC, OK, AUT],
    ("editar", status.EM_EXECUCAO): [OK, OK, OK, NAOENC, OK, AUT],
    ("editar", status.CONCLUIDA): [PERM, PERM, PERM, NAOENC, OK, AUT],
    ("iniciar", status.ABERTA): [OK, OK, OK, NAOENC, OK, AUT],
    ("iniciar", status.EM_EXECUCAO): [PERM, PERM, PERM, NAOENC, PERM, AUT],
    ("iniciar", status.CONCLUIDA): [PERM, PERM, PERM, NAOENC, PERM, AUT],
    ("desfazer", status.ABERTA): [PERM, PERM, PERM, NAOENC, PERM, AUT],
    ("desfazer", status.EM_EXECUCAO): [PERM, PERM, OK, NAOENC, OK, AUT],
    ("desfazer", status.CONCLUIDA): [PERM, PERM, PERM, NAOENC, PERM, AUT],
    ("concluir", status.ABERTA): [PERM, PERM, PERM, NAOENC, PERM, AUT],
    ("concluir", status.EM_EXECUCAO): [PERM, PERM, OK, NAOENC, OK, AUT],
    ("concluir", status.CONCLUIDA): [PERM, PERM, PERM, NAOENC, PERM, AUT],
}
CELULAS = [
    (ator, acao, st, MATRIZ[(acao, st)][i])
    for (acao, st) in MATRIZ
    for i, ator in enumerate(ATORES)
]
FLAG_DA_ACAO = {
    "editar": "pode_editar",
    "iniciar": "pode_iniciar",
    "desfazer": "pode_desfazer_inicio",
    "concluir": "pode_concluir",
}


def executar(acao, ator_id, d):
    if acao == "editar":
        return ordens.editar_os(ator_id, d.id, d.versao, {"titulo": "Título alterado"})
    if acao == "iniciar":
        return ordens.iniciar_execucao(ator_id, d.id, d.versao)
    if acao == "desfazer":
        return ordens.desfazer_inicio(ator_id, d.id, d.versao)
    return concluir(ator_id, d)


def test_a_matriz_tem_72_celulas():
    assert len(CELULAS) == 6 * 4 * 3 == 72


@pytest.mark.parametrize(
    ("ator", "acao", "st", "esperado"), CELULAS, ids=[f"{a}-{ac}-{s}" for a, ac, s, _ in CELULAS]
)
def test_matriz_de_permissoes(cenario, ator, acao, st, esperado):
    d = preparar(cenario, st)
    antes = estado_bruto(d.id)

    # A flag de AcoesOs tem de concordar com o que a função realmente permite.
    if esperado in (OK, PERM):
        flag = getattr(ordens.obter_os(cenario[ator], d.id).acoes, FLAG_DA_ACAO[acao])
        assert flag is (esperado == OK)

    if esperado == OK:
        depois = executar(acao, cenario[ator], d)
        assert depois.versao == d.versao + 1
        assert estado_bruto(d.id) != antes
    else:
        with pytest.raises(esperado):
            executar(acao, cenario[ator], d)
        assert estado_bruto(d.id) == antes  # nada foi gravado


# --- Transições -----------------------------------------------------------------------


MOVIMENTOS = {(o, d) for o, d, _quem in status.TRANSICOES.values()}


def test_tabela_de_transicoes():
    assert MOVIMENTOS == {
        (status.ABERTA, status.EM_EXECUCAO),
        (status.EM_EXECUCAO, status.ABERTA),
        (status.EM_EXECUCAO, status.CONCLUIDA),
        (status.ABERTA, status.CANCELADA),
    }
    assert status.FINAIS == {status.CONCLUIDA, status.CANCELADA}


@pytest.mark.parametrize("origem", list(status.ROTULOS))
@pytest.mark.parametrize("destino", list(status.ROTULOS))
def test_transicao_fora_da_tabela_e_recusada_ate_para_admin(cenario, origem, destino):
    funcoes = {
        status.EM_EXECUCAO: lambda d: ordens.iniciar_execucao(cenario["admin"], d.id, d.versao),
        status.ABERTA: lambda d: ordens.desfazer_inicio(cenario["admin"], d.id, d.versao),
        status.CONCLUIDA: lambda d: concluir(cenario["admin"], d),
        status.CANCELADA: lambda d: ordens.cancelar(cenario["admin"], d.id, d.versao),
    }
    d = preparar(cenario, origem)
    if (origem, destino) in MOVIMENTOS:
        assert funcoes[destino](d).status == destino
    else:
        with pytest.raises(ErroPermissao):
            funcoes[destino](d)
        assert ordens.obter_os(cenario["admin"], d.id).status == origem


def test_iniciar_define_executor_e_evento(cenario):
    d = criar(cenario["marina"])
    d = ordens.iniciar_execucao(cenario["joao"], d.id, d.versao)
    assert (d.status, d.executor_id, d.executor_nome) == (
        status.EM_EXECUCAO,
        cenario["joao"],
        "João Fictício",
    )
    assert d.inicio_execucao_em == T0 and d.versao == 2 and d.atualizado_em == T0
    assert eventos(cenario, d.id) == [
        ("CRIACAO", None, None, None),
        ("ITEM_ADICIONADO", "item 1", None, "Outros | Valor total | 1 x R$\u00a0100,00"),
        ("STATUS", "status", "ABERTA", "EM_EXECUCAO"),
    ]


def test_quem_iniciou_e_o_unico_usuario_comum_que_conclui_ou_desfaz(cenario):
    d = criar(cenario["marina"])
    d = ordens.iniciar_execucao(cenario["joao"], d.id, d.versao)  # A = joao
    for b in (cenario["pedro"], cenario["marina"]):  # B, da mesma filial
        with pytest.raises(ErroPermissao):
            concluir(b, d)
        with pytest.raises(ErroPermissao):
            ordens.desfazer_inicio(b, d.id, d.versao)
    assert concluir(cenario["joao"], d).status == status.CONCLUIDA  # A pode

    outra = criar(cenario["marina"])
    outra = ordens.iniciar_execucao(cenario["joao"], outra.id, outra.versao)
    assert ordens.desfazer_inicio(cenario["joao"], outra.id, outra.versao).status == "ABERTA"

    terceira = criar(cenario["marina"])
    terceira = ordens.iniciar_execucao(cenario["joao"], terceira.id, terceira.versao)
    feita = concluir(cenario["admin"], terceira)  # o admin também pode
    assert (feita.concluido_por_id, feita.executor_id) == (cenario["admin"], cenario["joao"])


def test_apos_desfazer_outro_usuario_inicia_e_vira_executor(cenario):
    d = criar(cenario["marina"])
    d = ordens.iniciar_execucao(cenario["joao"], d.id, d.versao)
    d = ordens.desfazer_inicio(cenario["joao"], d.id, d.versao)
    assert (d.status, d.executor_id, d.executor_nome, d.inicio_execucao_em) == (
        status.ABERTA,
        None,
        None,
        None,
    )
    d = ordens.iniciar_execucao(cenario["pedro"], d.id, d.versao)
    assert d.executor_id == cenario["pedro"]
    with pytest.raises(ErroPermissao):  # joao deixou de ser o executor
        concluir(cenario["joao"], d)
    assert [e[3] for e in eventos(cenario, d.id) if e[0] == "STATUS"] == [
        "EM_EXECUCAO",
        "ABERTA",
        "EM_EXECUCAO",
    ]


# --- concluir_os ----------------------------------------------------------------------


def test_concluir_preenche_realizado_e_eventos(cenario):
    d = preparar(cenario, status.EM_EXECUCAO)
    c = concluir(cenario["pedro"], d, descricao_realizado="  Rolamento trocado.  ")
    assert c.status == status.CONCLUIDA
    assert (c.concluido_por_id, c.concluido_por_nome, c.concluida_em) == (
        cenario["pedro"],
        "Pedro Modelo",
        T0,
    )
    assert (c.resumo_custos.total_realizado_centavos, c.inicio_realizado, c.fim_realizado) == (
        12000,
        INICIO,
        FIM,
    )
    assert c.descricao_realizado == "Rolamento trocado." and c.versao == d.versao + 1
    assert eventos(cenario, d.id)[3:] == [  # depois de CRIACAO, item previsto e início
        ("STATUS", "status", "EM_EXECUCAO", "CONCLUIDA"),
        ("REALIZADO", "inicio_realizado", None, INICIO.isoformat()),
        ("REALIZADO", "fim_realizado", None, FIM.isoformat()),
        ("REALIZADO", "descricao_realizado", None, "Rolamento trocado."),
        ("REALIZADO", "nota_conclusao", None, "Serviço feito conforme o previsto."),
        ("ITEM_ADICIONADO", "item 2", None, "Outros | Valor total | 1 x R$\u00a0120,00"),
    ]


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("valor_realizado_centavos", None),
        ("valor_realizado_centavos", -1),
        ("valor_realizado_centavos", 10_000_000_000),
        ("valor_realizado_centavos", "120"),
        ("valor_realizado_centavos", 1.5),
        ("inicio_realizado", None),
        ("inicio_realizado", "2026-05-04 09:00"),
        ("inicio_realizado", datetime(2026, 5, 4, 9, 0)),  # sem fuso
        ("fim_realizado", None),
        ("fim_realizado", datetime(2026, 5, 4, 10, 30)),  # sem fuso
        ("fim_realizado", INICIO - timedelta(minutes=1)),  # fim antes do início
        ("fim_realizado", INICIO),  # fim igual ao início
        ("fim_realizado", T0 + timedelta(minutes=6)),  # no futuro, além da tolerância
        ("descricao_realizado", None),
        ("descricao_realizado", ""),
        ("descricao_realizado", "   "),
        ("descricao_realizado", "d" * 2001),
    ],
)
def test_concluir_recusa_campo_ausente_ou_invalido(cenario, campo, valor):
    d = preparar(cenario, status.EM_EXECUCAO)
    antes = estado_bruto(d.id)
    with pytest.raises(ErroValidacao) as info:
        concluir(cenario["pedro"], d, **{campo: valor})
    # o valor realizado virou item de custo: é validado como valor unitário do item
    esperado = "valor_unitario_centavos" if campo == "valor_realizado_centavos" else campo
    assert info.value.campo == esperado and info.value.mensagem
    assert estado_bruto(d.id) == antes


def test_concluir_limites_de_tempo(cenario):
    d = preparar(cenario, status.EM_EXECUCAO)
    with pytest.raises(ErroValidacao) as info:  # duração acima de 59.999 minutos
        concluir(cenario["pedro"], d, inicio_realizado=FIM - timedelta(minutes=60_000))
    assert info.value.campo == "fim_realizado"
    c = concluir(
        cenario["pedro"],
        d,
        inicio_realizado=T0 + timedelta(minutes=5) - timedelta(minutes=59_999),
        fim_realizado=T0 + timedelta(minutes=5),  # exatamente no limite da tolerância
    )
    assert c.tempo_realizado_minutos == 59_999


def test_concluir_converte_o_fuso_para_utc(cenario):
    from zoneinfo import ZoneInfo

    sp = ZoneInfo("America/Sao_Paulo")
    d = preparar(cenario, status.EM_EXECUCAO)
    c = concluir(
        cenario["pedro"],
        d,
        inicio_realizado=datetime(2026, 5, 4, 6, 50, tzinfo=sp),
        fim_realizado=datetime(2026, 5, 4, 7, 30, tzinfo=sp),
    )
    assert c.inicio_realizado == datetime(2026, 5, 4, 9, 50, tzinfo=UTC)
    assert c.inicio_realizado.utcoffset() == timedelta(0)
    assert c.tempo_realizado_minutos == 40


# --- editar_os ------------------------------------------------------------------------


def test_editar_dois_campos_grava_dois_eventos(cenario):
    d = criar(cenario["marina"])
    e = ordens.editar_os(
        cenario["marina"],
        d.id,
        d.versao,
        {
            "titulo": "  Troca do motor  ",
            "tempo_previsto_minutos": 90,
            "descricao": "Esteira com ruído.",
        },  # dois não mudam
    )
    assert (e.titulo, e.tempo_previsto_minutos, e.versao) == ("Troca do motor", 90, 2)
    assert eventos(cenario, d.id)[2:] == [  # depois de CRIACAO e do item previsto
        ("EDICAO", "titulo", "Troca de rolamento", "Troca do motor"),
        ("EDICAO", "tempo_previsto_minutos", "60", "90"),
    ]


@pytest.mark.parametrize("campo", ["valor_previsto_centavos", "valor_realizado_centavos"])
def test_editar_os_nao_aceita_mais_preco_unico(cenario, campo):
    """O preço único saiu (prompt 13): valores só mudam pelos itens de custo."""
    d = preparar(cenario, status.CONCLUIDA)
    for ator in ("marina", "admin"):
        with pytest.raises(ErroPermissao):
            ordens.editar_os(cenario[ator], d.id, d.versao, {campo: 100})
    assert ordens.obter_os(cenario["admin"], d.id).versao == d.versao


def test_edicao_sem_mudanca_nao_grava_evento_nem_muda_versao(cenario):
    d = criar(cenario["marina"])
    for alteracoes in ({}, {"titulo": "Troca de rolamento"}, {"titulo": " Troca de rolamento "}):
        e = ordens.editar_os(cenario["marina"], d.id, d.versao, alteracoes)
        assert e == d
    assert eventos(cenario, d.id) == [
        ("CRIACAO", None, None, None),
        ("ITEM_ADICIONADO", "item 1", None, "Outros | Valor total | 1 x R$\u00a0100,00"),
    ]


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("titulo", "ab"),
        ("titulo", "t" * 121),
        ("descricao", " "),
        ("descricao", "d" * 2001),
        ("tempo_previsto_minutos", 0),
        ("tempo_previsto_minutos", 60_000),
    ],
)
def test_editar_usa_a_mesma_validacao_de_criar(cenario, campo, valor):
    d = criar(cenario["marina"])
    with pytest.raises(ErroValidacao) as info:
        ordens.editar_os(
            cenario["marina"],
            d.id,
            d.versao,
            {campo: valor, "titulo": "Outro"} if campo != "titulo" else {campo: valor},
        )
    assert info.value.campo == campo
    assert ordens.obter_os(cenario["marina"], d.id) == d  # nada foi gravado


@pytest.mark.parametrize("ator", ["marina", "pedro", "admin"])
@pytest.mark.parametrize("st", [status.ABERTA, status.EM_EXECUCAO])
@pytest.mark.parametrize("campo", ordens.CAMPOS_REALIZADO)
def test_realizado_nao_e_gravado_por_edicao_antes_da_conclusao(cenario, ator, st, campo):
    d = preparar(cenario, st)
    valores = {
        "valor_realizado_centavos": 500,
        "inicio_realizado": INICIO,
        "fim_realizado": FIM,
        "descricao_realizado": "Feito.",
    }
    antes = estado_bruto(d.id)
    with pytest.raises(ErroPermissao):
        ordens.editar_os(cenario[ator], d.id, d.versao, {campo: valores[campo]})
    assert estado_bruto(d.id) == antes


@pytest.mark.parametrize(
    "campo", ["status", "numero", "versao", "criado_por_id", "executor_id", "id", "inexistente"]
)
def test_campo_desconhecido_ou_proibido(cenario, campo):
    d = criar(cenario["marina"])
    for ator in ("marina", "admin"):
        with pytest.raises(ErroPermissao):
            ordens.editar_os(cenario[ator], d.id, d.versao, {campo: "x", "titulo": "Novo título"})
    assert ordens.obter_os(cenario["marina"], d.id) == d


def test_depois_de_concluida_so_admin_edita_inclusive_o_realizado(cenario):
    c = preparar(cenario, status.CONCLUIDA)
    for ator in ("marina", "pedro"):  # criadora e executor
        with pytest.raises(ErroPermissao):
            ordens.editar_os(cenario[ator], c.id, c.versao, {"titulo": "Não pode"})
        with pytest.raises(ErroPermissao):
            ordens.editar_os(cenario[ator], c.id, c.versao, {"valor_realizado_centavos": 1})

    novo_fim = FIM + timedelta(minutes=30)
    e = ordens.editar_os(
        cenario["admin"],
        c.id,
        c.versao,
        {
            "titulo": "Título corrigido",
            "fim_realizado": novo_fim,
            "descricao_realizado": "Texto corrigido.",
        },
    )
    assert (e.titulo, e.fim_realizado, e.descricao_realizado) == (
        "Título corrigido",
        novo_fim,
        "Texto corrigido.",
    )
    assert e.tempo_realizado_minutos == 120 and e.status == status.CONCLUIDA
    assert eventos(cenario, c.id)[-3:] == [
        ("EDICAO", "titulo", "Troca de rolamento", "Título corrigido"),
        ("EDICAO", "fim_realizado", FIM.isoformat(), novo_fim.isoformat()),
        ("EDICAO", "descricao_realizado", "Rolamento trocado.", "Texto corrigido."),
    ]


def test_admin_corrigindo_realizado_passa_pela_validacao(cenario):
    c = preparar(cenario, status.CONCLUIDA)
    for alteracoes, campo in [
        ({"fim_realizado": INICIO - timedelta(minutes=1)}, "fim_realizado"),
        ({"inicio_realizado": FIM + timedelta(minutes=1)}, "fim_realizado"),
        ({"fim_realizado": T0 + timedelta(hours=1)}, "fim_realizado"),
        ({"inicio_realizado": datetime(2026, 5, 4, 9, 0)}, "inicio_realizado"),
        ({"descricao_realizado": ""}, "descricao_realizado"),
    ]:
        with pytest.raises(ErroValidacao) as info:
            ordens.editar_os(cenario["admin"], c.id, c.versao, alteracoes)
        assert info.value.campo == campo
    assert ordens.obter_os(cenario["admin"], c.id) == replace(
        c,
        acoes=c.acoes.__class__(
            pode_editar=True,
            pode_iniciar=False,
            pode_desfazer_inicio=False,
            pode_concluir=False,
            pode_editar_realizado=True,
            pode_editar_itens_previstos=True,
            pode_editar_itens_realizados=True,
            pode_excluir=True,  # prompt 24: o administrador pode mandar para a Lixeira
        ),
    )


def test_so_admin_muda_a_filial(cenario):
    d = criar(cenario["marina"])
    with pytest.raises(ErroPermissao):
        ordens.editar_os(cenario["marina"], d.id, d.versao, {"filial_id": cenario["f2"]})
    with pytest.raises(ErroPermissao):  # nem para a própria filial: o campo é proibido
        ordens.editar_os(cenario["marina"], d.id, d.versao, {"filial_id": cenario["f1"]})
    assert ordens.obter_os(cenario["marina"], d.id).filial_id == cenario["f1"]

    with pytest.raises(ErroValidacao):
        ordens.editar_os(cenario["admin"], d.id, d.versao, {"filial_id": 9999})
    e = ordens.editar_os(cenario["admin"], d.id, d.versao, {"filial_id": cenario["f2"]})
    assert e.filial_codigo == "F002"
    assert eventos(cenario, d.id)[-1] == ("EDICAO", "filial_id", "F001", "F002")
    with pytest.raises(ErroNaoEncontrado):  # a criadora deixou de ver a OS
        ordens.obter_os(cenario["marina"], d.id)
    assert ordens.obter_os(cenario["carlos"], d.id).id == d.id


# --- Trava otimista -------------------------------------------------------------------


@pytest.mark.parametrize("versao", [0, 2, 99, None, "1", True])
def test_versao_desatualizada_gera_conflito_e_nao_muda_nada(cenario, versao):
    d = criar(cenario["marina"])
    antes = estado_bruto(d.id)
    with pytest.raises(ErroConflito):
        ordens.editar_os(cenario["marina"], d.id, versao, {"titulo": "Outro título"})
    with pytest.raises(ErroConflito):
        ordens.iniciar_execucao(cenario["joao"], d.id, versao)
    assert estado_bruto(d.id) == antes

    iniciada = ordens.iniciar_execucao(cenario["joao"], d.id, d.versao)
    antes = estado_bruto(d.id)
    with pytest.raises(ErroConflito):
        ordens.desfazer_inicio(cenario["joao"], d.id, d.versao)  # versão antiga
    with pytest.raises(ErroConflito):
        concluir(cenario["joao"], d)  # versão antiga
    assert estado_bruto(d.id) == antes
    assert concluir(cenario["joao"], iniciada).versao == iniciada.versao + 1


def test_duas_edicoes_com_a_mesma_versao(cenario):
    d = criar(cenario["marina"])
    ordens.editar_os(cenario["marina"], d.id, d.versao, {"titulo": "Primeira gravação"})
    with pytest.raises(ErroConflito):
        ordens.editar_os(cenario["admin"], d.id, d.versao, {"titulo": "Segunda gravação"})
    assert ordens.obter_os(cenario["admin"], d.id).titulo == "Primeira gravação"


def test_se_o_evento_falha_a_alteracao_e_desfeita(cenario, monkeypatch):
    d = criar(cenario["marina"])
    antes = estado_bruto(d.id)

    def falhar(*_a, **_k):
        raise RuntimeError("falha simulada ao gravar o evento")

    monkeypatch.setattr(ordens, "registrar_evento", falhar)
    with pytest.raises(RuntimeError):
        ordens.editar_os(cenario["marina"], d.id, d.versao, {"titulo": "Não deve ficar"})
    with pytest.raises(RuntimeError):
        ordens.iniciar_execucao(cenario["joao"], d.id, d.versao)
    assert estado_bruto(d.id) == antes


# --- Diferenças -----------------------------------------------------------------------


def test_diferencas_sao_none_antes_da_conclusao(cenario):
    for st in (status.ABERTA, status.EM_EXECUCAO):
        d = preparar(cenario, st)
        assert (d.tempo_realizado_minutos, d.diferenca_tempo_minutos) == (None, None)
        assert d.resumo_custos.total_realizado_centavos == 0  # nada realizado ainda


@pytest.mark.parametrize(
    ("previsto", "realizado", "minutos", "esperado"),
    [
        # (valor previsto, valor realizado, minutos realizados) -> (dif. valor, %, dif. tempo)
        (10000, 12000, 90, (2000, 20.0, 30)),  # acima do previsto
        (10000, 7500, 45, (-2500, -25.0, -15)),  # abaixo do previsto
        (10000, 10000, 60, (0, 0.0, 0)),  # igual ao previsto
        (0, 5000, 60, (5000, None, 0)),  # previsto zero: sem percentual
        (0, 0, 60, (0, None, 0)),
        (30000, 10000, 61, (-20000, -66.67, 1)),  # percentual arredondado
    ],
)
def test_diferencas(cenario, previsto, realizado, minutos, esperado):
    d = preparar(cenario, status.EM_EXECUCAO, valor_previsto_centavos=previsto)
    c = concluir(
        cenario["pedro"],
        d,
        valor_realizado_centavos=realizado,
        fim_realizado=INICIO + timedelta(minutes=minutos),
    )
    assert c.tempo_realizado_minutos == minutos
    assert (
        c.resumo_custos.diferenca_centavos,
        c.resumo_custos.diferenca_percentual,
        c.diferenca_tempo_minutos,
    ) == esperado


def test_acoes_por_ator_em_cada_status(cenario):
    def flags(ator, d):
        a = ordens.obter_os(cenario[ator], d.id).acoes
        return (
            a.pode_editar,
            a.pode_iniciar,
            a.pode_desfazer_inicio,
            a.pode_concluir,
            a.pode_editar_realizado,
        )

    aberta = preparar(cenario, status.ABERTA)
    assert flags("marina", aberta) == (True, True, False, False, False)
    assert flags("joao", aberta) == (True, True, False, False, False)  # manutenção da filial
    execucao = preparar(cenario, status.EM_EXECUCAO)
    assert flags("marina", execucao) == (True, False, False, False, False)
    assert flags("pedro", execucao) == (True, False, True, True, False)  # manutenção edita
    assert flags("admin", execucao) == (True, False, True, True, False)
    concluida = preparar(cenario, status.CONCLUIDA)
    assert flags("marina", concluida) == (False,) * 5
    assert flags("pedro", concluida) == (False,) * 5
    assert flags("admin", concluida) == (True, False, False, False, True)
