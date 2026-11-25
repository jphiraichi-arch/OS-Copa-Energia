"""Prompt 47: check-up final da versão Flet (partes A, B e C), pelos serviços.

Banco local novo (fixture ``banco``), filial 1007 criada como pelo seed e os usuários de
teste criados pelo mesmo serviço da tela de administração (``usuarios.criar_usuario``):
'usuario', 'usuario2', 'manutencao', 'manutencao2' e o administrador. Os nomes com cara
de papel são um pedido explícito deste check-up.

Cada recusa esperada é conferida com a exceção exata. O resultado vai para
docs/CHECKUP_FINAL.md (tabela papel x ação).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from osapp import formatacao
from osapp.services import (
    administracao,
    custos,
    especialidades,
    lixeira,
    motivos_cancelamento,
    ordens,
    relatorios,
    relogio,
    sla,
    usuarios,
    visualizacoes,
)
from osapp.services.auth import autenticar
from osapp.services.erros import (
    ErroAutenticacao,
    ErroPermissao,
    ErroTrocaDeSenhaPendente,
    ErroValidacao,
)
from osapp.ui import fase_custo, historico, leitura, rotulos_eventos
from tests.fabricas import categoria_id, especialidade_id, motivo_id, tipo_id

SENHA_ADMIN = "senha-do-admin-123"
SENHA_NOVA = "Senha-Definitiva-2026"
# 25/11/2026 14:00 em São Paulo (UTC-3).
T0 = datetime(2026, 11, 25, 17, 0, tzinfo=UTC)

# Campos que o papel usuario nunca pode receber.
PROIBIDOS_USUARIO = {
    "itens",
    "resumo_custos",
    "total_previsto_centavos",
    "total_realizado_centavos",
    "tem_itens_previstos",
    "sem_gasto_previsto",
    "sem_gasto_realizado",
    "tempo_previsto_minutos",
    "inicio_realizado",
    "fim_realizado",
    "descricao_realizado",
    "executor_id",
    "executor_nome",
    "prioridade",
    "eventos",
    "visualizacoes",
}


class Relogio:
    def __init__(self) -> None:
        self.agora = T0

    def __call__(self):
        return self.agora

    def andar(self, **delta) -> None:
        self.agora += timedelta(**delta)


@pytest.fixture
def clock(monkeypatch):
    r = Relogio()
    monkeypatch.setattr(relogio, "agora", r)
    monkeypatch.setenv("OS_TZ", "America/Sao_Paulo")
    return r


@pytest.fixture
def g(banco, clock):
    """Filial 1007 e os cinco usuários do check-up, todos já com a senha trocada."""
    filial = administracao.criar_filial("1007", "Jardinópolis")
    outra = administracao.criar_filial("2001", "Filial de teste")
    admin = administracao.criar_usuario("Administrador", "admin", SENHA_ADMIN, "1007", True).id
    ids = {"f": filial.id, "outra": outra.id, "admin": admin}
    for login, papel in (
        ("usuario", "usuario"),
        ("usuario2", "usuario"),
        ("manutencao", "manutencao"),
        ("manutencao2", "manutencao"),
    ):
        gerada = usuarios.criar_usuario(admin, login.capitalize(), login, filial.id, papel)
        assert gerada.usuario.deve_trocar_senha is True  # troca obrigatória no 1º login
        usuarios.trocar_propria_senha(gerada.usuario.id, gerada.senha_temporaria, SENHA_NOVA)
        ids[login] = gerada.usuario.id
    return ids


def _sol(g, quem="usuario", titulo="Vazamento na bomba", urgencia="alta"):
    return ordens.criar_solicitacao(g[quem], titulo, "Óleo no piso perto da bomba 2.", urgencia)


def _assumir(g, os_id, quem="manutencao", **extra):
    """O que a tela 'Assumir' grava: previsto (tempo, tipo, especialidade) e um item."""
    d = ordens.obter_os(g[quem], os_id)
    d = ordens.editar_os(
        g[quem],
        os_id,
        d.versao,
        {
            "tempo_previsto_minutos": 90,
            "tipo_id": tipo_id(),
            "especialidade_id": especialidade_id(),
            **extra,
        },
    )
    return custos.adicionar_item(
        g[quem],
        os_id,
        d.versao,
        custos.FASE_PREVISTO,
        categoria_id("PECAS_MATERIAIS"),
        "Retentor",
        Decimal("1"),
        12000,
    )


def _concluir(g, os_id, quem="manutencao", **extra):
    d = ordens.obter_os(g[quem], os_id)
    inicio = d.inicio_execucao_em
    if relogio.agora() <= inicio:  # o fim não pode estar no futuro: o relógio anda
        relogio.agora.andar(minutes=60)
    dados = {
        "itens_realizados": [
            custos.ItemEntrada(categoria_id("PECAS_MATERIAIS"), "Retentor", Decimal("1"), 9000)
        ],
        "inicio_realizado": inicio,
        "fim_realizado": relogio.agora(),
        "descricao_realizado": "Troca do retentor.",
        "nota_conclusao": "Vazamento resolvido.",
    }
    dados.update(extra)
    return ordens.concluir_os(g[quem], os_id, d.versao, **dados)


def _campos(obj) -> set[str]:
    return {f.name for f in dataclasses.fields(obj)}


# =====================================================================================
# PARTE A - PAPÉIS
# =====================================================================================

# --- usuario / usuario2 ----------------------------------------------------------------


def test_a_usuario_cria_solicitacao_com_filial_travada(g):
    v = _sol(g)
    assert (v.status, v.urgencia, v.filial_codigo) == ("ABERTA", "alta", "1007")
    with pytest.raises(ErroPermissao):  # outra filial: só o administrador escolhe
        ordens.criar_solicitacao(g["usuario"], "Outra filial", "Desc.", "baixa", g["outra"])


def test_a_usuario_ve_todas_as_ordens_da_filial_sem_custo(g):
    a = _sol(g, "usuario", "Pedido do usuario")
    b = _sol(g, "usuario2", "Pedido do usuario2")
    c = ordens.criar_os(
        g["manutencao"],
        "Preventiva da caldeira",
        "Rotina.",
        [custos.ItemEntrada(categoria_id(), "Serviço", Decimal("1"), 50000)],
        60,
    )
    for quem in ("usuario", "usuario2"):
        pagina = ordens.listar_os(g[quem])
        assert {i.id for i in pagina.itens} == {a.id, b.id, c.id}
        for item in pagina.itens:
            assert not (_campos(item) & PROIBIDOS_USUARIO), _campos(item) & PROIBIDOS_USUARIO
        for os_id in (a.id, b.id, c.id):
            visao = ordens.obter_os(g[quem], os_id)
            assert type(visao).__name__ == "OsVisaoSolicitante"
            assert not (_campos(visao) & PROIBIDOS_USUARIO)
        with pytest.raises(ErroPermissao):  # sem histórico de eventos
            ordens.listar_eventos(g[quem], c.id)


def test_a_usuario2_nao_edita_nem_cancela_do_usuario(g):
    v = _sol(g)
    with pytest.raises(ErroPermissao):
        ordens.editar_solicitacao(g["usuario2"], v.id, v.versao, {"titulo": "Mudado por outro"})
    with pytest.raises(ErroPermissao):
        ordens.cancelar(g["usuario2"], v.id, v.versao, motivo_id())
    assert not ordens.obter_os(g["usuario2"], v.id).acoes.pode_editar


def test_a_usuario_edita_e_cancela_a_propria_so_aberta(g):
    v = _sol(g)
    v = ordens.editar_solicitacao(
        g["usuario"], v.id, v.versao, {"titulo": "Vazamento grande", "urgencia": "emergencial"}
    )
    assert (v.titulo, v.urgencia) == ("Vazamento grande", "emergencial")
    cancelada = ordens.cancelar(g["usuario"], v.id, v.versao, motivo_id())
    assert cancelada.status == "CANCELADA"
    # Outra, que sai de Aberta (a manutenção inicia): o solicitante não edita nem cancela.
    w = _sol(g, titulo="Lâmpada queimada", urgencia="baixa")
    d = _assumir(g, w.id)
    ordens.iniciar_execucao(g["manutencao"], w.id, d.versao)
    w = ordens.obter_os(g["usuario"], w.id)
    with pytest.raises(ErroPermissao):
        ordens.editar_solicitacao(g["usuario"], w.id, w.versao, {"titulo": "Depois do início"})
    with pytest.raises(ErroPermissao):
        ordens.cancelar(g["usuario"], w.id, w.versao, motivo_id())


def test_a_usuario_sem_acesso_a_areas_da_manutencao_e_admin(g):
    v = _sol(g)
    u = g["usuario"]
    recusas = [
        lambda: relatorios.relatorio_mensal(u, 2026, 11),
        lambda: lixeira.listar_excluidas(u),
        lambda: lixeira.excluir_os(u, v.id, v.versao, "Motivo qualquer."),
        lambda: usuarios.listar_usuarios(u),
        lambda: sla.listar_alvos(u),
        lambda: sla.definir_alvo(u, g["f"], "alta", 60, 120),
        lambda: ordens.criar_os(u, "Título", "Descrição."),
        lambda: ordens.editar_os(u, v.id, v.versao, {"prioridade": "alta"}),
        lambda: ordens.iniciar_execucao(u, v.id, v.versao),
        lambda: custos.adicionar_item(
            u, v.id, v.versao, custos.FASE_PREVISTO, categoria_id(), "X", Decimal("1"), 100
        ),
        lambda: especialidades.criar(u, "Nova"),
        lambda: motivos_cancelamento.criar(u, "Novo"),
    ]
    for recusa in recusas:
        with pytest.raises(ErroPermissao):
            recusa()


# --- manutencao / manutencao2 -------------------------------------------------------------


def test_a_manutencao_ve_tudo_com_custos(g):
    _sol(g)
    c = ordens.criar_os(
        g["manutencao2"],
        "Preventiva",
        "Rotina.",
        [custos.ItemEntrada(categoria_id(), "Serviço", Decimal("2"), 2500)],
        60,
    )
    itens = ordens.listar_os(g["manutencao"]).itens
    assert len(itens) == 2
    assert {i.id: i.total_previsto_centavos for i in itens}[c.id] == 5000
    assert ordens.obter_os(g["manutencao"], c.id).resumo_custos.total_previsto_centavos == 5000


def test_a_iniciar_recusado_ate_as_pendencias_com_motivos(g):
    v = _sol(g)
    with pytest.raises(ErroValidacao) as erro:
        ordens.iniciar_execucao(g["manutencao"], v.id, v.versao)
    msg = erro.value.mensagem
    for pendencia in ("tempo previsto", "tipo", "especialidade"):
        assert pendencia in msg.lower(), msg
    assert "custo" in msg.lower() or "sem gasto" in msg.lower(), msg
    d = _assumir(g, v.id)
    assert d.pendencias_para_iniciar == ()
    # Prioridade: a urgência preenche ao iniciar; a urgência não muda.
    iniciada = ordens.iniciar_execucao(g["manutencao"], v.id, d.versao)
    assert (iniciada.prioridade, iniciada.urgencia) == ("alta", "alta")


def test_a_manutencao2_nao_conclui_nem_desfaz_o_inicio_de_outro(g):
    v = _sol(g)
    d = _assumir(g, v.id)
    d = ordens.iniciar_execucao(g["manutencao"], v.id, d.versao)
    with pytest.raises(ErroPermissao):
        ordens.desfazer_inicio(g["manutencao2"], v.id, d.versao)
    with pytest.raises(ErroPermissao):
        _concluir(g, v.id, quem="manutencao2")
    d = ordens.desfazer_inicio(g["manutencao"], v.id, d.versao)  # o executor pode
    assert d.status == "ABERTA" and d.executor_id is None
    d = ordens.iniciar_execucao(g["manutencao"], v.id, d.versao)
    concluida = _concluir(g, v.id, quem="admin")  # o administrador pode
    assert concluida.status == "CONCLUIDA"


def test_a_os_direta_sem_gasto_e_itens(g):
    d = ordens.criar_os(
        g["manutencao"],
        "Ajuste de portão",
        "Portão arrastando.",
        None,
        30,
        tipo_id=tipo_id(),
        prioridade="media",
        especialidade_id=especialidade_id(),
        sem_gasto_previsto=True,
    )
    assert d.origem == "manutencao" and d.sem_gasto_previsto is True
    d = ordens.definir_sem_gasto(g["manutencao"], d.id, d.versao, custos.FASE_PREVISTO, False)
    d = custos.adicionar_item(
        g["manutencao"],
        d.id,
        d.versao,
        custos.FASE_PREVISTO,
        categoria_id(),
        "Graxa",
        Decimal("1"),
        1500,
    )
    item = d.itens[0]
    d = custos.editar_item(
        g["manutencao"], d.id, item.id, d.versao, {"valor_unitario_centavos": 2000}
    )
    assert d.resumo_custos.total_previsto_centavos == 2000
    d = custos.remover_item(g["manutencao"], d.id, d.itens[0].id, d.versao)
    assert d.itens == () or list(d.itens) == []
    d = ordens.definir_sem_gasto(g["manutencao"], d.id, d.versao, custos.FASE_PREVISTO, True)
    d = ordens.iniciar_execucao(g["manutencao"], d.id, d.versao)
    # Conclusão: realizado (item ou Sem gasto), horários e nota são obrigatórios.
    with pytest.raises(ErroValidacao):
        _concluir(g, d.id, itens_realizados=[])
    with pytest.raises(ErroValidacao):
        _concluir(g, d.id, nota_conclusao="")
    concluida = _concluir(g, d.id, itens_realizados=[], sem_gasto_realizado=True)
    assert concluida.status == "CONCLUIDA" and concluida.sem_gasto_realizado is True


def test_a_manutencao_sem_acesso_a_admin_e_sem_mudar_urgencia_ou_filial(g):
    v = _sol(g)
    m = g["manutencao"]
    recusas = [
        lambda: usuarios.listar_usuarios(m),
        lambda: sla.definir_alvo(m, g["f"], "alta", 60, 120),
        lambda: lixeira.excluir_os(m, v.id, v.versao, "Motivo qualquer."),
        lambda: lixeira.listar_excluidas(m),
        lambda: ordens.editar_solicitacao(m, v.id, v.versao, {"urgencia": "baixa"}),
        lambda: ordens.editar_os(m, v.id, v.versao, {"filial_id": g["outra"]}),
        lambda: especialidades.criar(m, "Nova"),
        lambda: motivos_cancelamento.criar(m, "Novo"),
    ]
    for recusa in recusas:
        with pytest.raises(ErroPermissao):
            recusa()


# --- admin -----------------------------------------------------------------------------


def test_a_admin_filial_nos_dois_formularios(g):
    s = ordens.criar_solicitacao(g["admin"], "Na outra filial", "Desc.", "media", g["outra"])
    o = ordens.criar_os(g["admin"], "OS na outra filial", "Desc.", filial_id=g["outra"])
    assert s.filial_codigo == o.filial_codigo == "2001"


def test_a_admin_edita_concluida_cancela_exclui_e_restaura(g):
    v = _sol(g)
    d = _assumir(g, v.id)
    d = ordens.iniciar_execucao(g["manutencao"], v.id, d.versao)
    d = _concluir(g, v.id)
    with pytest.raises(ErroPermissao):  # a manutenção não mexe na concluída
        ordens.editar_os(g["manutencao"], v.id, d.versao, {"descricao_realizado": "Outra."})
    d = ordens.editar_os(g["admin"], v.id, d.versao, {"descricao_realizado": "Corrigido."})
    assert d.descricao_realizado == "Corrigido."
    d = custos.adicionar_item(
        g["admin"],
        v.id,
        d.versao,
        custos.FASE_REALIZADO,
        categoria_id(),
        "Extra",
        Decimal("1"),
        1000,
    )
    assert d.resumo_custos.total_realizado_centavos == 10000
    # Cancelar qualquer Aberta, com motivo.
    w = _sol(g, "usuario2", "Outra")
    with pytest.raises(ErroValidacao):
        ordens.cancelar(g["admin"], w.id, w.versao)  # sem motivo
    assert ordens.cancelar(g["admin"], w.id, w.versao, motivo_id()).status == "CANCELADA"
    # Excluir com motivo e restaurar com o mesmo número.
    numero = d.numero
    r = lixeira.excluir_os(g["admin"], v.id, d.versao, "Aberta em duplicidade.")
    assert v.id not in {i.id for i in ordens.listar_os(g["admin"]).itens}
    assert [i.numero for i in lixeira.listar_excluidas(g["admin"]).itens] == [numero]
    restaurada = lixeira.restaurar_os(g["admin"], v.id, r.versao)
    assert restaurada.numero == numero
    assert v.id in {i.id for i in ordens.listar_os(g["admin"]).itens}


def test_a_admin_usuarios_sla_especialidades_motivos(g, clock):
    a = g["admin"]
    nova = usuarios.criar_usuario(a, "Davi Melo", "davi.melo", g["f"], "manutencao", [g["f"]])
    u = nova.usuario
    u = usuarios.alterar_usuario(a, u.id, u.versao, {"filiais": [g["f"], g["outra"]]})
    assert set(u.filiais_codigos) == {"1007", "2001"}
    usuarios.trocar_propria_senha(u.id, nova.senha_temporaria, SENHA_NOVA)
    # Redefinir senha: troca obrigatória e o próximo uso é recusado até trocar.
    u = usuarios.obter_usuario(a, u.id)
    gerada = usuarios.redefinir_senha(a, u.id, u.versao)
    assert autenticar("davi.melo", gerada.senha_temporaria).deve_trocar_senha is True
    with pytest.raises(ErroTrocaDeSenhaPendente):
        ordens.listar_os(u.id)
    usuarios.trocar_propria_senha(u.id, gerada.senha_temporaria, "Outra-Senha-Longa-9")
    assert ordens.listar_os(u.id).itens == ()
    # Desativar: recusado na próxima ação.
    u = usuarios.obter_usuario(a, u.id)
    usuarios.alterar_usuario(a, u.id, u.versao, {"ativo": False})
    with pytest.raises(ErroAutenticacao):
        ordens.listar_os(u.id)
    # SLA, especialidades, motivos.
    alvo = sla.definir_alvo(a, g["f"], "alta", 120, 1440)
    assert (alvo.prazo_inicio_min, alvo.prazo_solucao_min) == (120, 1440)
    assert especialidades.criar(a, "Refrigeração").nome == "Refrigeração"
    assert motivos_cancelamento.criar(a, "Sem peça").nome == "Sem peça"


# =====================================================================================
# PARTE B - VALORES (comportamento atual; o pedido de 'dígitos pela direita' é outra
# regra, ver docs/CHECKUP_FINAL.md)
# =====================================================================================


@pytest.mark.parametrize(
    ("digitado", "minutos", "texto"),
    [
        ("1", 60, "1:00"),  # 1 ou 2 dígitos = horas inteiras (regra do prompt 22)
        ("15", 900, "15:00"),
        ("150", 110, "1:50"),
        ("1500", 900, "15:00"),
        ("219", 139, "2:19"),
        ("1000", 600, "10:00"),
        ("1:30", 90, "1:30"),
    ],
)
def test_b_duracao_atual(digitado, minutos, texto):
    lido = leitura.ler_duracao(digitado)
    assert (lido.valor, lido.texto, lido.erro) == (minutos, texto, None)


def test_b_minutos_e_hora_invalidos():
    assert leitura.ler_duracao("175").erro == leitura.MSG_MINUTOS  # 1:75
    assert leitura.ler_hora("2400").erro == leitura.MSG_HORA
    assert leitura.ler_hora("2359").valor.isoformat() == "23:59:00"


@pytest.mark.parametrize(
    ("digitado", "centavos"),
    [
        ("1", 100),  # dígitos = reais inteiros (regra do prompt 22)
        ("15", 1500),
        ("1500", 150000),
        ("2,19", 219),
        ("1.234,56", 123456),
        ("10,00", 1000),
    ],
)
def test_b_dinheiro_atual(digitado, centavos):
    assert leitura.ler_dinheiro(digitado).valor == centavos


def test_b_dinheiro_limite():
    assert leitura.ler_dinheiro("99.999.999,99").valor == leitura.VALOR_MAX_CENTAVOS
    assert leitura.ler_dinheiro("100.000.000,00").erro == leitura.MSG_DINHEIRO_MAX


def test_b_totais():
    assert custos.total_da_linha(Decimal("1.5"), 3333) == 5000  # R$ 49,995 -> R$ 50,00
    assert formatacao.formatar_brl(5000) == "R$ 50,00"
    assert fase_custo.texto_da_lista(False, False, 0) == "—"
    assert fase_custo.exibicao(False, False, 0).pill == "A DEFINIR"
    assert fase_custo.texto_da_lista(False, True, 0) == "Sem gasto"
    assert "R$" not in fase_custo.exibicao(False, False, 0).total


def test_b_diferencas():
    assert historico.texto_diferenca_valor(12000, 12.0).endswith("acima do previsto (+12%)")
    assert "abaixo do previsto" in historico.texto_diferenca_valor(-12000, -12.0)
    assert historico.texto_diferenca_valor(0, 0.0) == "Igual ao previsto"
    assert historico.texto_diferenca_valor(15000, None) == "+R$ 150,00 (não previsto)"
    assert historico.texto_diferenca_valor(0, None) == "R$ 0,00 — sem gasto"
    tempo = historico.texto_diferenca_tempo(-178)
    assert tempo == "2h58 abaixo do previsto" and "-" not in tempo and "−" not in tempo
    resumo = custos.calcular_resumo([])  # nada previsto: sem divisão por zero
    assert resumo.diferenca_percentual is None


def test_b_datas_no_fuso_incluindo_23h30(g, clock):
    clock.agora = datetime(2026, 11, 26, 2, 30, tzinfo=UTC)  # 25/11 23:30 em São Paulo
    v = _sol(g)
    assert formatacao.formatar_data_hora(v.aberta_em) == "25/11/2026 23:30"
    assert formatacao.formatar_data(v.aberta_em) == "25/11/2026"


def test_b_numeros_consecutivos_nunca_reutilizados_e_busca(g):
    a, b = _sol(g), _sol(g, titulo="Segunda")
    seq_a, seq_b = int(a.numero.rsplit("-", 1)[1]), int(b.numero.rsplit("-", 1)[1])
    assert seq_b == seq_a + 1 and a.numero.startswith("1007-")
    ordens.cancelar(g["admin"], b.id, b.versao, motivo_id())
    va = ordens.obter_os(g["admin"], a.id)
    lixeira.excluir_os(g["admin"], a.id, va.versao, "Teste de numeração.")
    c = _sol(g, titulo="Terceira")
    assert int(c.numero.rsplit("-", 1)[1]) == seq_b + 1
    assert [i.id for i in ordens.listar_os(g["manutencao"], busca=c.numero).itens] == [c.id]


# =====================================================================================
# PARTE C - COMPORTAMENTO
# =====================================================================================


def test_c_ciclo_completo_historico_legivel_e_contadores(g, clock):
    def contagem():
        c = ordens.contadores(g["manutencao"])
        return c.abertas, c.em_execucao

    assert contagem() == (0, 0)
    v = _sol(g)
    assert contagem() == (1, 0)
    d = _assumir(g, v.id)
    d = ordens.iniciar_execucao(g["manutencao"], v.id, d.versao)
    assert contagem() == (0, 1)
    d = ordens.desfazer_inicio(g["manutencao"], v.id, d.versao)
    assert contagem() == (1, 0)
    d = ordens.iniciar_execucao(g["manutencao"], v.id, d.versao)
    _concluir(g, v.id)
    assert contagem() == (0, 0)
    w = _sol(g, titulo="Cancelável")
    assert contagem() == (1, 0)
    ordens.cancelar(g["usuario"], w.id, w.versao, motivo_id())
    assert contagem() == (0, 0)
    for os_id in (v.id, w.id):
        for evento in ordens.listar_eventos(g["admin"], os_id):
            frase = historico.frase(evento)
            assert rotulos_eventos.CAMPO_DESCONHECIDO not in frase, frase
            assert "_" not in frase.split(":")[0], frase  # nenhum nome de coluna


def test_c_filtros_busca_e_escopo(g):
    s = _sol(g, titulo="Balança desregulada")
    o = ordens.criar_os(
        g["manutencao"],
        "Pintura",
        "Parede.",
        [custos.ItemEntrada(categoria_id(), "Tinta acrílica", Decimal("1"), 100)],
    )
    m = g["manutencao"]

    def ids(**k):
        return {i.id for i in ordens.listar_os(m, **k).itens}

    assert ids(origem="solicitacao") == {s.id}  # 'Abertas pela operação'
    assert ids(status="ABERTA") == {s.id, o.id}
    assert ids(nao_visualizadas=True) == {s.id}
    assert ids(busca="balanca", escopo=ordens.ESCOPO_TUDO) == {s.id}  # sem acento
    assert ids(busca="BALANÇA", escopo=ordens.ESCOPO_TUDO) == {s.id}
    assert ids(busca="tinta", escopo=ordens.ESCOPO_ITENS) == {o.id}
    assert ids(busca="balanca", escopo=ordens.ESCOPO_ITENS) == set()  # só itens


def test_c_visualizada_so_pela_manutencao_no_detalhe(g):
    v = _sol(g)
    ordens.listar_os(g["manutencao"])  # lista não conta
    for quem in ("usuario", "admin"):
        assert visualizacoes.registrar_visualizacao(g[quem], v.id) is False
    assert ordens.obter_os(g["usuario"], v.id).visualizada is False
    assert visualizacoes.registrar_visualizacao(g["manutencao"], v.id) is True
    assert ordens.obter_os(g["usuario"], v.id).visualizada is True


def test_c_etiquetas_de_sla_com_relogio(g, clock):
    v = _sol(g, urgencia="emergencial")  # início em 60 min
    assert ordens.obter_os(g["manutencao"], v.id).sla.texto == "No prazo"
    clock.andar(minutes=50)
    assert ordens.obter_os(g["manutencao"], v.id).sla.texto == "Vence em 10 min"
    clock.andar(minutes=20)
    assert ordens.obter_os(g["manutencao"], v.id).sla.texto == "Atrasada"


def test_c_relatorio_bate_com_a_conta_a_mao(g, clock):
    # Novembro/2026: 3 solicitações; 1 concluída (início 30 min e solução 2 h depois de
    # aberta), 1 cancelada, 1 aberta. Conta a mão: abertas no mês = 3, concluídas = 1,
    # canceladas = 1, ainda abertas = 1; tempo até o início = 30 min; solução = 120 min.
    a = _sol(g, titulo="Primeira")
    b = _sol(g, titulo="Segunda")
    _sol(g, titulo="Terceira")
    d = _assumir(g, a.id)
    clock.andar(minutes=30)
    ordens.iniciar_execucao(g["manutencao"], a.id, d.versao)
    clock.andar(minutes=90)
    _concluir(g, a.id)
    ordens.cancelar(g["admin"], b.id, b.versao, motivo_id())
    clock.andar(minutes=5)
    r = relatorios.relatorio_mensal(g["admin"], 2026, 11)
    mes = r.mes_selecionado
    assert mes.fluxo.abertas == 3
    assert mes.fluxo.concluidas == 1
    assert mes.fluxo.canceladas == 1
    assert mes.resposta.media_segundos == 30 * 60  # aberta -> início
    assert mes.solucao.media_segundos == 120 * 60  # aberta -> conclusão
