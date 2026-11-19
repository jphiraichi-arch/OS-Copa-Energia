"""Relatórios mensais de Ordens de Serviço.

Níveis de acesso (decididos aqui, nunca na interface):
- Relatório básico: contagens e tempos, sem valores em dinheiro nem dados por pessoa.
  Todo usuário ativo vê o da própria filial; administrador vê qualquer filial ou todas.
- Relatório completo: valores previstos e realizados (gasto do mês), desvios, as OS com
  maior estouro e o desempenho por executor. Gerente vê o da própria filial;
  administrador vê qualquer filial ou o consolidado. Os demais recebem ``completo=None``.
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
from osapp.services import custos, relogio
from osapp.services import status as _status
from osapp.services.auth import Ator, carregar_ator
from osapp.services.erros import ErroPermissao, ErroValidacao
from osapp.services.ordens import NIVEIS
from osapp.services.permissoes import pode_ver_relatorio_completo

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
    completo: RelatorioCompleto | None  # None quando o ator não pode ver


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
    if not ator.is_admin:
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

        completo = None
        if pode_ver_relatorio_completo(ator, filial_efetiva):
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
    """Solicitações ainda ABERTA agora (ignora período e status)."""

    quantidade: int
    mais_antiga_segundos: int | None  # agora - aberta_em da mais antiga


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
    total_no_periodo: int  # OS consideradas (com ou sem início)


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


def relatorio_tempos(
    ator_id: int,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    status: object = None,
    filial_id: int | None = None,
) -> RelatorioTempos:
    """Tempos de resposta e até a solução das solicitações. Manutenção (própria filial) e
    administrador (uma filial ou todas); o papel usuario recebe ErroPermissao."""
    ator = carregar_ator(ator_id)
    if ator.is_usuario:
        logger.warning("Permissão negada: usuario_id=%s ação=relatório de tempos.", ator.usuario_id)
        raise ErroPermissao()
    tz = carregar_config().tz
    data_inicio, data_fim = _validar_periodo(data_inicio, data_fim, tz)
    status_escolhidos = _validar_status(status)
    inicio, fim = limites_do_periodo(data_inicio, data_fim, tz)
    agora = relogio.agora()
    with sessao() as s:
        filial, rotulo = _filial_permitida(s, ator, filial_id)
        repo = OrdemServicoRepo(s)
        linhas = repo.tempos_de_solicitacoes(filial, inicio, fim, status_escolhidos)
        abertas = repo.abertas_de_solicitacoes(filial)
    respostas = {n: [] for n in NIVEIS}
    solucoes = {n: [] for n in NIVEIS}
    todas_resp, todas_sol = [], []
    for _id, urgencia, aberta, inicio_exec, concluida in linhas:
        if inicio_exec is not None:
            valor = _segundos(aberta, inicio_exec)
            todas_resp.append(valor)
            respostas.setdefault(urgencia, []).append(valor)
        if concluida is not None:
            valor = _segundos(aberta, concluida)
            todas_sol.append(valor)
            solucoes.setdefault(urgencia, []).append(valor)
    mais_antiga = min(abertas) if abertas else None
    return RelatorioTempos(
        data_inicio=data_inicio,
        data_fim=data_fim,
        status=status_escolhidos,
        filial_id=filial,
        filial_rotulo=rotulo,
        resposta=medir(todas_resp),
        solucao=medir(todas_sol),
        por_urgencia=tuple(
            TemposPorUrgencia(n, medir(respostas[n]), medir(solucoes[n])) for n in NIVEIS
        ),
        backlog=Backlog(
            len(abertas), _segundos(mais_antiga, agora) if mais_antiga is not None else None
        ),
        total_no_periodo=len(linhas),
    )
