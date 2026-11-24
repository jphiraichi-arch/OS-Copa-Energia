"""Relatórios mensais de Ordens de Serviço.

Acesso (decidido aqui, nunca na interface; decisão de 21/11/2026):
- manutenção: o relatório da própria filial, com custos (básico e completo);
- administrador: qualquer filial ou o consolidado de todas, com custos;
- papel usuario: nenhum (ErroPermissao).
O relatório básico tem contagens e tempos; o completo, valores previstos e realizados,
desvios, as OS com maior estouro e o desempenho por executor. O sinalizador de gerente
não muda mais o acesso.
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from osapp.config import carregar_config
from osapp.db import sessao
from osapp.repositories import FilialRepo, OrdemServicoRepo
from osapp.services import custos, linha_do_tempo, ordens, relogio
from osapp.services import status as _status
from osapp.services.auth import Ator, carregar_ator
from osapp.services.erros import ErroPermissao, ErroValidacao
from osapp.services.permissoes import pode_ver_relatorio_mensal

logger = logging.getLogger(__name__)

ANO_MIN = 2000
ANO_MAX = 2100
MAIORES_DESVIOS = 5
TODAS_AS_FILIAIS = "Todas as filiais"


@dataclass(frozen=True)
class ContagemStatus:
    status: str
    rotulo: str
    total: int


@dataclass(frozen=True)
class RelatorioBasico:
    por_status: tuple[ContagemStatus, ...]  # situação atual, um item por status conhecido
    criadas_no_mes: int
    concluidas_no_mes: int
    tempo_medio_execucao_minutos: int | None  # das concluídas no mês; None se nenhuma


@dataclass(frozen=True)
class DesvioOs:
    os_id: int
    numero: str
    titulo: str
    filial_codigo: str
    valor_previsto_centavos: int
    valor_realizado_centavos: int
    diferenca_centavos: int


@dataclass(frozen=True)
class LinhaExecutor:
    nome: str
    concluidas: int
    valor_realizado_centavos: int
    tempo_realizado_minutos: int


@dataclass(frozen=True)
class LinhaFilial:
    filial_codigo: str
    concluidas: int
    valor_realizado_centavos: int


@dataclass(frozen=True)
class RelatorioCompleto:
    valor_previsto_centavos: int  # das OS concluídas no mês
    valor_realizado_centavos: int  # gasto total do mês
    diferenca_valor_centavos: int
    diferenca_valor_percentual: float | None  # None quando o previsto é 0
    tempo_previsto_minutos: int
    tempo_realizado_minutos: int
    diferenca_tempo_minutos: int
    acima_do_previsto: int  # quantas OS concluídas custaram mais que o previsto
    maiores_desvios: tuple[DesvioOs, ...]
    por_executor: tuple[LinhaExecutor, ...]
    por_filial: tuple[LinhaFilial, ...]  # só no consolidado de todas as filiais


@dataclass(frozen=True)
class Relatorio:
    ano: int
    mes: int
    filial_id: int | None  # None = todas as filiais
    filial_rotulo: str
    basico: RelatorioBasico
    completo: RelatorioCompleto | None  # sempre preenchido desde 21/11/2026


def _e_int(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def limites_do_mes(ano: int, mes: int, tz: str) -> tuple[datetime, datetime]:
    """[início, fim) do mês no fuso ``tz``, em UTC."""
    fuso = ZoneInfo(tz)
    inicio = datetime(ano, mes, 1, tzinfo=fuso)
    proximo = (
        datetime(ano + 1, 1, 1, tzinfo=fuso)
        if mes == 12
        else datetime(ano, mes + 1, 1, tzinfo=fuso)
    )
    return inicio.astimezone(UTC), proximo.astimezone(UTC)


def _minutos(inicio: datetime, fim: datetime) -> int:
    return int((fim - inicio).total_seconds() // 60)


def _filial_permitida(s, ator: Ator, filial_id: object) -> tuple[int | None, str]:
    """Filial efetiva e seu rótulo, aplicando a regra de visibilidade."""
    if filial_id is not None and not _e_int(filial_id):
        raise ErroValidacao("filial_id", "Filial inválida.")
    if not ator.e_admin:
        if filial_id is not None and filial_id != ator.filial_id:
            logger.warning(
                "Permissão negada: usuario_id=%s ação=relatório de outra filial.", ator.usuario_id
            )
            raise ErroPermissao()
        filial_id = ator.filial_id
    if filial_id is None:
        return None, TODAS_AS_FILIAIS
    filial = FilialRepo(s).obter(filial_id)
    if filial is None:
        raise ErroValidacao("filial_id", "Filial não encontrada.")
    return filial.id, f"{filial.codigo} - {filial.nome}"


def gerar_relatorio(ator_id: int, ano: int, mes: int, filial_id: int | None = None) -> Relatorio:
    """Relatório do mês (no fuso OS_TZ). ``filial_id`` None: a própria filial, ou todas
    as filiais para administrador."""
    ator = carregar_ator(ator_id)
    if ator.e_usuario:
        logger.warning("Permissão negada: usuario_id=%s ação=relatório mensal.", ator.usuario_id)
        raise ErroPermissao()
    if not _e_int(ano) or not ANO_MIN <= ano <= ANO_MAX:
        raise ErroValidacao("ano", "Ano inválido.")
    if not _e_int(mes) or not 1 <= mes <= 12:
        raise ErroValidacao("mes", "Mês inválido.")
    inicio, fim = limites_do_mes(ano, mes, carregar_config().tz)

    with sessao() as s:
        filial_efetiva, rotulo = _filial_permitida(s, ator, filial_id)
        repo = OrdemServicoRepo(s)
        contagem = repo.contar_por_status(filial_efetiva)
        concluidas = repo.listar_concluidas(filial_efetiva, _status.CONCLUIDA, inicio, fim)

        com_periodo = [
            o for o in concluidas if o.inicio_realizado is not None and o.fim_realizado is not None
        ]
        tempos = [_minutos(o.inicio_realizado, o.fim_realizado) for o in com_periodo]
        basico = RelatorioBasico(
            por_status=tuple(
                ContagemStatus(st, rotulo_st, contagem.get(st, 0))
                for st, rotulo_st in _status.ROTULOS.items()
            ),
            criadas_no_mes=repo.contar_criadas(filial_efetiva, inicio, fim),
            concluidas_no_mes=len(concluidas),
            tempo_medio_execucao_minutos=round(sum(tempos) / len(tempos)) if tempos else None,
        )

        if not pode_ver_relatorio_mensal(ator, filial_efetiva):  # defesa extra
            raise ErroPermissao()
        completo = _completo(concluidas, consolidado=filial_efetiva is None)

        return Relatorio(
            ano=ano,
            mes=mes,
            filial_id=filial_efetiva,
            filial_rotulo=rotulo,
            basico=basico,
            completo=completo,
        )


def _totais(ordem) -> tuple[int, int]:
    """(previsto, realizado) da OS, somados dos itens de custo."""
    previsto = realizado = 0
    for item in ordem.itens:
        total = custos.total_da_linha(item.quantidade, item.valor_unitario_centavos)
        if item.fase == custos.FASE_PREVISTO:
            previsto += total
        else:
            realizado += total
    return previsto, realizado


def _completo(concluidas, consolidado: bool) -> RelatorioCompleto:
    totais = {o.id: _totais(o) for o in concluidas}
    previsto = sum(p for p, _ in totais.values())
    realizado = sum(r for _, r in totais.values())
    tempo_previsto = sum(o.tempo_previsto_minutos for o in concluidas)
    tempo_realizado = sum(
        _minutos(o.inicio_realizado, o.fim_realizado)
        for o in concluidas
        if o.inicio_realizado is not None and o.fim_realizado is not None
    )
    desvios = sorted(
        (
            DesvioOs(
                os_id=o.id,
                numero=o.numero,
                titulo=o.titulo,
                filial_codigo=o.filial.codigo,
                valor_previsto_centavos=totais[o.id][0],
                valor_realizado_centavos=totais[o.id][1],
                diferenca_centavos=totais[o.id][1] - totais[o.id][0],
            )
            for o in concluidas
        ),
        key=lambda d: (-d.diferenca_centavos, d.numero),
    )
    por_executor: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    por_filial: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for o in concluidas:
        pessoa = o.executor or o.concluido_por
        linha = por_executor[pessoa.nome if pessoa else "-"]
        linha[0] += 1
        linha[1] += totais[o.id][1]
        if o.inicio_realizado is not None and o.fim_realizado is not None:
            linha[2] += _minutos(o.inicio_realizado, o.fim_realizado)
        filial = por_filial[o.filial.codigo]
        filial[0] += 1
        filial[1] += totais[o.id][1]
    return RelatorioCompleto(
        valor_previsto_centavos=previsto,
        valor_realizado_centavos=realizado,
        diferenca_valor_centavos=realizado - previsto,
        diferenca_valor_percentual=custos.percentual(realizado - previsto, previsto),
        tempo_previsto_minutos=tempo_previsto,
        tempo_realizado_minutos=tempo_realizado,
        diferenca_tempo_minutos=tempo_realizado - tempo_previsto,
        acima_do_previsto=sum(1 for d in desvios if d.diferenca_centavos > 0),
        maiores_desvios=tuple(d for d in desvios if d.diferenca_centavos > 0)[:MAIORES_DESVIOS],
        por_executor=tuple(
            LinhaExecutor(nome, *valores)
            for nome, valores in sorted(por_executor.items(), key=lambda i: (-i[1][0], i[0]))
        ),
        por_filial=tuple(
            LinhaFilial(codigo, *valores) for codigo, valores in sorted(por_filial.items())
        )
        if consolidado
        else (),
    )


# --- Relatório de tempos de atendimento (prompt 18) -----------------------------------
#
# Tempo de resposta = inicio_execucao_em - aberta_em (só OS com início).
# Tempo até solução = concluida_em - aberta_em (só concluídas).
# População: origem 'solicitacao', nunca CANCELADA, filial do ator (admin: uma ou todas),
# aberta no período (dias corridos em OS_TZ, inclusive). Horas corridas, sem expediente.

DIAS_PADRAO = 30
STATUS_DO_RELATORIO = (_status.ABERTA, _status.EM_EXECUCAO, _status.CONCLUIDA)


@dataclass(frozen=True)
class Medida:
    """n, média e mediana em segundos inteiros (None quando n = 0)."""

    n: int
    media_segundos: int | None
    mediana_segundos: int | None


@dataclass(frozen=True)
class TemposPorUrgencia:
    urgencia: str
    resposta: Medida
    solucao: Medida


@dataclass(frozen=True)
class Backlog:
    """Solicitações ainda ABERTA agora (ignora período e status; respeita a busca)."""

    quantidade: int
    mais_antiga_segundos: int | None  # agora - aberta_em da mais antiga
    filtrado_por: str | None = None  # o termo de busca aplicado, se houver


@dataclass(frozen=True)
class CustosBusca:
    """Custos das OS que correspondem à busca (calculados com custos.calcular_resumo)."""

    previsto_total_centavos: int  # todas as OS correspondentes
    concluidas: int  # quantas das correspondentes estão CONCLUIDA
    previsto_concluidas_centavos: int
    realizado_concluidas_centavos: int
    diferenca_centavos: int  # realizado - previsto, só concluídas
    diferenca_percentual: float | None  # None quando o previsto das concluídas é 0


@dataclass(frozen=True)
class LinhaBusca:
    os_id: int
    numero: str
    titulo: str
    status: str
    urgencia: str | None
    aberta_em: datetime
    previsto_centavos: int
    realizado_centavos: int | None  # só quando CONCLUIDA


@dataclass(frozen=True)
class ResultadoBusca:
    termo: str
    escopo: str
    correspondentes: int
    total_periodo: int  # população do relatório sem a busca
    percentual: float | None  # None quando total_periodo é 0
    custos: CustosBusca
    ordens: tuple[LinhaBusca, ...]  # a página pedida, mais recentes primeiro
    pagina: int
    total_paginas: int


@dataclass(frozen=True)
class RelatorioTempos:
    data_inicio: date
    data_fim: date
    status: tuple[str, ...]
    filial_id: int | None  # None = todas as filiais (só administrador)
    filial_rotulo: str
    resposta: Medida
    solucao: Medida
    por_urgencia: tuple[TemposPorUrgencia, ...]  # baixa, media, alta, emergencial
    backlog: Backlog
    total_no_periodo: int  # OS consideradas (com ou sem início), já filtradas pela busca
    busca: ResultadoBusca | None = None  # só quando há termo de busca


def _arredondar(valor: Decimal) -> int:
    return int(valor.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def medir(segundos: list[int]) -> Medida:
    """Média (meio para cima) e mediana em segundos inteiros. Lista vazia: n = 0, None."""
    if not segundos:
        return Medida(0, None, None)
    media = _arredondar(Decimal(sum(segundos)) / Decimal(len(segundos)))
    mediana = _arredondar(Decimal(str(statistics.median(segundos))))
    return Medida(len(segundos), media, mediana)


def limites_do_periodo(data_inicio: date, data_fim: date, tz: str) -> tuple[datetime, datetime]:
    """[início do 1º dia, início do dia seguinte ao último) em OS_TZ, convertidos para UTC."""
    zona = ZoneInfo(tz)
    inicio = datetime.combine(data_inicio, time.min, tzinfo=zona).astimezone(UTC)
    fim = datetime.combine(data_fim + timedelta(days=1), time.min, tzinfo=zona).astimezone(UTC)
    return inicio, fim


def _segundos(inicio: datetime, fim: datetime) -> int:
    return int((fim - inicio).total_seconds())


def _validar_periodo(data_inicio: object, data_fim: object, tz: str) -> tuple[date, date]:
    if data_inicio is None and data_fim is None:
        hoje = relogio.agora().astimezone(ZoneInfo(tz)).date()
        return hoje - timedelta(days=DIAS_PADRAO - 1), hoje
    for campo, valor in (("data_inicio", data_inicio), ("data_fim", data_fim)):
        if not isinstance(valor, date) or isinstance(valor, datetime):
            raise ErroValidacao(campo, "Informe a data no formato dd/mm/aaaa.")
    if data_fim < data_inicio:
        raise ErroValidacao("data_fim", "A data final deve ser igual ou depois da inicial.")
    return data_inicio, data_fim


def _validar_status(status: object) -> tuple[str, ...]:
    if status is None:
        return STATUS_DO_RELATORIO
    if not isinstance(status, list | tuple | set | frozenset) or not status:
        raise ErroValidacao("status", "Escolha pelo menos um status.")
    if not set(status) <= set(STATUS_DO_RELATORIO):
        raise ErroValidacao("status", "Status inválido.")
    return tuple(s for s in STATUS_DO_RELATORIO if s in status)


POR_PAGINA_BUSCA = 50


def _medidas(linhas) -> tuple[Medida, Medida, tuple[TemposPorUrgencia, ...]]:
    """Resposta e solução (geral e por urgência) das linhas de tempos_de_solicitacoes."""
    respostas = {n: [] for n in ordens.NIVEIS}
    solucoes = {n: [] for n in ordens.NIVEIS}
    todas_resp, todas_sol = [], []
    for _id, urgencia, aberta, inicio_exec, concluida, *_resto in linhas:
        if inicio_exec is not None:
            valor = _segundos(aberta, inicio_exec)
            todas_resp.append(valor)
            respostas.setdefault(urgencia, []).append(valor)
        if concluida is not None:
            valor = _segundos(aberta, concluida)
            todas_sol.append(valor)
            solucoes.setdefault(urgencia, []).append(valor)
    por_urgencia = tuple(
        TemposPorUrgencia(n, medir(respostas[n]), medir(solucoes[n])) for n in ordens.NIVEIS
    )
    return medir(todas_resp), medir(todas_sol), por_urgencia


def _validar_pagina(pagina: object) -> int:
    if not _e_int(pagina) or pagina < 1:
        raise ErroValidacao("pagina", "Página inválida.")
    return pagina


def _resultado_busca(repo, termo, escopo, linhas, total_periodo, pagina) -> ResultadoBusca:
    """Contagem, custos e lista paginada das OS que correspondem à busca."""
    itens_por_os: dict[int, list] = defaultdict(list)
    for item in repo.itens_das_ordens([linha[0] for linha in linhas]):
        itens_por_os[item.os_id].append(custos.item_dto(item))
    resumos = {linha[0]: custos.calcular_resumo(itens_por_os[linha[0]]) for linha in linhas}
    concluidas = [linha[0] for linha in linhas if linha[5] == _status.CONCLUIDA]
    resumo_concluidas = custos.calcular_resumo(
        item for os_id in concluidas for item in itens_por_os[os_id]
    )
    recentes = sorted(linhas, key=lambda linha: (linha[2], linha[0]), reverse=True)
    total_paginas = max(1, -(-len(recentes) // POR_PAGINA_BUSCA))
    pagina = min(pagina, total_paginas)
    trecho = recentes[(pagina - 1) * POR_PAGINA_BUSCA : pagina * POR_PAGINA_BUSCA]
    return ResultadoBusca(
        termo=termo,
        escopo=escopo,
        correspondentes=len(linhas),
        total_periodo=total_periodo,
        percentual=custos.percentual(len(linhas), total_periodo),
        custos=CustosBusca(
            previsto_total_centavos=sum(r.total_previsto_centavos for r in resumos.values()),
            concluidas=len(concluidas),
            previsto_concluidas_centavos=resumo_concluidas.total_previsto_centavos,
            realizado_concluidas_centavos=resumo_concluidas.total_realizado_centavos,
            diferenca_centavos=resumo_concluidas.diferenca_centavos,
            diferenca_percentual=resumo_concluidas.diferenca_percentual,
        ),
        ordens=tuple(
            LinhaBusca(
                os_id=os_id,
                numero=numero,
                titulo=titulo,
                status=situacao,
                urgencia=urgencia,
                aberta_em=aberta,
                previsto_centavos=resumos[os_id].total_previsto_centavos,
                realizado_centavos=(
                    resumos[os_id].total_realizado_centavos
                    if situacao == _status.CONCLUIDA
                    else None
                ),
            )
            for os_id, urgencia, aberta, _i, _c, situacao, numero, titulo in trecho
        ),
        pagina=pagina,
        total_paginas=total_paginas,
    )


def relatorio_tempos(
    ator_id: int,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    status: object = None,
    filial_id: int | None = None,
    termo: object = None,
    escopo: str | None = ordens.ESCOPO_ITENS,
    pagina: int = 1,
) -> RelatorioTempos:
    """Tempos de resposta e até a solução das solicitações. Manutenção (própria filial) e
    administrador (uma filial ou todas); o papel usuario recebe ErroPermissao.

    ``termo`` e ``escopo`` (prompt 22) restringem o relatório INTEIRO às OS que
    correspondem à busca (ordens.condicao_busca); com termo, ``busca`` traz a contagem
    sobre o total do período, os custos e a lista paginada (50 por página).
    """
    ator = carregar_ator(ator_id)
    if ator.e_usuario:
        logger.warning("Permissão negada: usuario_id=%s ação=relatório de tempos.", ator.usuario_id)
        raise ErroPermissao()
    tz = carregar_config().tz
    data_inicio, data_fim = _validar_periodo(data_inicio, data_fim, tz)
    status_escolhidos = _validar_status(status)
    escopo = ordens.validar_escopo(escopo)
    pagina = _validar_pagina(pagina)
    condicao = ordens.condicao_busca(termo, escopo, ator)
    inicio, fim = limites_do_periodo(data_inicio, data_fim, tz)
    agora = relogio.agora()
    busca = None
    with sessao() as s:
        filial, rotulo = _filial_permitida(s, ator, filial_id)
        repo = OrdemServicoRepo(s)
        linhas = repo.tempos_de_solicitacoes(filial, inicio, fim, status_escolhidos, condicao)
        abertas = repo.abertas_de_solicitacoes(filial, condicao)
        if condicao is not None:
            total_periodo = len(repo.tempos_de_solicitacoes(filial, inicio, fim, status_escolhidos))
            busca = _resultado_busca(
                repo, termo.strip()[: ordens.BUSCA_MAX], escopo, linhas, total_periodo, pagina
            )
    resposta, solucao, por_urgencia = _medidas(linhas)
    mais_antiga = min(abertas) if abertas else None
    return RelatorioTempos(
        data_inicio=data_inicio,
        data_fim=data_fim,
        status=status_escolhidos,
        filial_id=filial,
        filial_rotulo=rotulo,
        resposta=resposta,
        solucao=solucao,
        por_urgencia=por_urgencia,
        backlog=Backlog(
            len(abertas),
            _segundos(mais_antiga, agora) if mais_antiga is not None else None,
            busca.termo if busca is not None else None,
        ),
        total_no_periodo=len(linhas),
        busca=busca,
    )


# --- Relatório mensal: mês selecionado e acumulado (prompt 25) -------------------------
#
# Substitui o período livre do prompt 18 por um mês M (00:00 do dia 1 até 00:00 do dia 1
# de M+1 em OS_TZ, fim exclusivo). Acumulado: da primeira ordem até o FIM de M.
# População: origem 'solicitacao', não excluída (filtro central), escopo de filial do
# ator e a busca do prompt 22 (no mês e no acumulado). O status de cada ordem é o do fim
# do período, refeito pelos eventos (linha_do_tempo.situacao_em), nunca o atual.
# - Fluxo: abertas (aberta_em no período), concluídas e canceladas (evento no período,
#   abertas quando for). O filtro de status não se aplica ao fluxo nem à taxa.
# - Taxa de conclusão, sobre as abertas no período: concluídas até o fim / (abertas -
#   canceladas até o fim).
# - Tempos, custos e lista: abertas no período cujo status no fim está no filtro; início
#   e conclusão só contam se aconteceram antes do fim (o início vale se não foi desfeito
#   antes do fim). Mesmas funções do prompt 18 (_medidas) e do 22 (_resultado_busca).


@dataclass(frozen=True)
class Fluxo:
    abertas: int
    concluidas: int
    canceladas: int


@dataclass(frozen=True)
class TaxaConclusao:
    numerador: int  # abertas no período e concluídas até o fim
    denominador: int  # abertas no período menos as canceladas até o fim
    percentual: float | None  # None quando o denominador é 0


@dataclass(frozen=True)
class ResumoDaBusca:
    correspondentes: int
    total: int  # a mesma população sem o termo
    percentual: float | None


@dataclass(frozen=True)
class BlocoMensal:
    inicio: datetime | None  # None no acumulado (desde a primeira ordem)
    fim: datetime  # exclusivo, em UTC
    fluxo: Fluxo
    taxa: TaxaConclusao
    resposta: Medida
    solucao: Medida
    por_urgencia: tuple[TemposPorUrgencia, ...]
    custos: CustosBusca
    busca: ResumoDaBusca | None  # só com termo


@dataclass(frozen=True)
class RelatorioMensal:
    ano: int
    mes: int
    filial_id: int | None
    filial_rotulo: str
    termo: str | None
    escopo: str
    status: tuple[str, ...]
    mes_selecionado: BlocoMensal
    acumulado: BlocoMensal
    ordens: tuple[LinhaBusca, ...]  # do mês, 50 por página, as mais recentes primeiro
    pagina: int
    total_paginas: int
    # Solicitações ABERTA agora (prompt 18; busca aplicada, decisão de 21/11). Não é do
    # período: é a situação no momento em que o relatório é tirado.
    backlog: Backlog | None = None


def taxa_de_conclusao(concluidas: int, abertas: int, canceladas: int) -> TaxaConclusao:
    """concluídas / (abertas - canceladas) x 100; None quando o denominador é 0."""
    denominador = abertas - canceladas
    return TaxaConclusao(concluidas, denominador, custos.percentual(concluidas, denominador))


def _no_periodo(instante: datetime | None, inicio: datetime | None, fim: datetime) -> bool:
    return instante is not None and (inicio is None or instante >= inicio) and instante < fim


def _bloco(repo, populacao, situacoes, ids_busca, termo, status, inicio, fim):
    """Um bloco (mês ou acumulado). ``populacao``: linhas de solicitacoes_ate sem a busca;
    ``ids_busca``: ids que correspondem ao termo (None sem termo)."""

    def casa(os_id: int) -> bool:
        return ids_busca is None or os_id in ids_busca

    abertas = [p for p in populacao if _no_periodo(p[2], inicio, fim)]
    filtradas = [p for p in abertas if casa(p[0])]
    sit = situacoes
    fluxo = Fluxo(
        abertas=len(filtradas),
        concluidas=sum(
            1 for p in populacao if casa(p[0]) and _no_periodo(sit[p[0]].concluida_em, inicio, fim)
        ),
        canceladas=sum(
            1 for p in populacao if casa(p[0]) and _no_periodo(sit[p[0]].cancelada_em, inicio, fim)
        ),
    )
    taxa = taxa_de_conclusao(
        sum(1 for p in filtradas if sit[p[0]].status == _status.CONCLUIDA),
        len(filtradas),
        sum(1 for p in filtradas if sit[p[0]].status == _status.CANCELADA),
    )

    def linhas(lista):
        # O mesmo formato de tempos_de_solicitacoes (prompt 18/22), com a situação do fim.
        return [
            (
                os_id,
                urgencia,
                aberta,
                sit[os_id].inicio,
                sit[os_id].concluida_em,
                sit[os_id].status,
                numero,
                titulo,
            )
            for os_id, urgencia, aberta, numero, titulo in lista
            if sit[os_id].status in status
        ]

    medidas = linhas(filtradas)
    resposta, solucao, por_urgencia = _medidas(medidas)
    total = len(linhas(abertas))
    resultado = _resultado_busca(repo, termo or "", ordens.ESCOPO_ITENS, medidas, total, 1)
    busca = (
        ResumoDaBusca(len(medidas), total, custos.percentual(len(medidas), total))
        if termo
        else None
    )
    bloco = BlocoMensal(
        inicio=inicio,
        fim=fim,
        fluxo=fluxo,
        taxa=taxa,
        resposta=resposta,
        solucao=solucao,
        por_urgencia=por_urgencia,
        custos=resultado.custos,
        busca=busca,
    )
    return bloco, medidas


def _validar_mes(ano: object, mes: object, tz: str) -> tuple[int, int]:
    if not _e_int(ano) or not ANO_MIN <= ano <= ANO_MAX:
        raise ErroValidacao("ano", "Ano inválido.")
    if not _e_int(mes) or not 1 <= mes <= 12:
        raise ErroValidacao("mes", "Mês inválido.")
    hoje = relogio.agora().astimezone(ZoneInfo(tz))
    if (ano, mes) > (hoje.year, hoje.month):
        raise ErroValidacao("mes", "Não é possível escolher um mês futuro.")
    return ano, mes


def relatorio_mensal(
    ator_id: int,
    ano: int,
    mes: int,
    termo: object = None,
    escopo: str | None = ordens.ESCOPO_ITENS,
    status: object = None,
    filial_id: int | None = None,
    pagina: int = 1,
) -> RelatorioMensal:
    """Mês selecionado e acumulado até o fim dele (ver o comentário acima). Manutenção
    (própria filial) e administrador (uma filial ou todas); usuario: ErroPermissao."""
    ator = carregar_ator(ator_id)
    if ator.e_usuario:
        logger.warning("Permissão negada: usuario_id=%s ação=relatório mensal.", ator.usuario_id)
        raise ErroPermissao()
    tz = carregar_config().tz
    ano, mes = _validar_mes(ano, mes, tz)
    status_escolhidos = _validar_status(status)
    escopo = ordens.validar_escopo(escopo)
    pagina = _validar_pagina(pagina)
    condicao = ordens.condicao_busca(termo, escopo, ator)
    termo_limpo = termo.strip()[: ordens.BUSCA_MAX] if condicao is not None else None
    inicio, fim = linha_do_tempo.periodo_do_mes(ano, mes, tz)
    with sessao() as s:
        filial, rotulo = _filial_permitida(s, ator, filial_id)
        repo = OrdemServicoRepo(s)
        populacao = repo.solicitacoes_ate(filial, fim)
        ids_busca = (
            {linha[0] for linha in repo.solicitacoes_ate(filial, fim, condicao)}
            if condicao is not None
            else None
        )
        marcos: dict[int, list] = defaultdict(list)
        for os_id, data_hora, tipo, valor_novo in repo.marcos_ate(filial, fim):
            marcos[os_id].append(linha_do_tempo.Marco(data_hora, tipo, valor_novo))
        situacoes = {p[0]: linha_do_tempo.situacao_em(marcos[p[0]], fim) for p in populacao}
        bloco_mes, linhas_do_mes = _bloco(
            repo, populacao, situacoes, ids_busca, termo_limpo, status_escolhidos, inicio, fim
        )
        acumulado, _ = _bloco(
            repo, populacao, situacoes, ids_busca, termo_limpo, status_escolhidos, None, fim
        )
        lista = _resultado_busca(
            repo, termo_limpo or "", escopo, linhas_do_mes, len(linhas_do_mes), pagina
        )
        abertas = repo.abertas_de_solicitacoes(filial, condicao)
    mais_antiga = min(abertas) if abertas else None
    backlog = Backlog(
        len(abertas),
        _segundos(mais_antiga, relogio.agora()) if mais_antiga is not None else None,
        termo_limpo,
    )
    return RelatorioMensal(
        ano=ano,
        mes=mes,
        filial_id=filial,
        filial_rotulo=rotulo,
        termo=termo_limpo,
        escopo=escopo,
        status=status_escolhidos,
        mes_selecionado=bloco_mes,
        acumulado=acumulado,
        ordens=lista.ordens,
        pagina=lista.pagina,
        total_paginas=lista.total_paginas,
        backlog=backlog,
    )
