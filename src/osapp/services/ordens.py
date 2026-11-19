"""Serviço de ordens de serviço.

Toda função pública recebe ``ator_id`` como primeiro argumento, começa por
``carregar_ator``, abre a própria sessão e devolve dataclasses congeladas (nunca
objetos do ORM). As regras de filial e de papel são aplicadas aqui.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm.exc import StaleDataError

from osapp.config import carregar_config
from osapp.db import sessao
from osapp.models import OrdemServico, OsEvento, OsItemCusto
from osapp.repositories import (
    CategoriaCustoRepo,
    EquipamentoRepo,
    FilialRepo,
    OrdemServicoRepo,
    OsEventoRepo,
    OsSequenciaRepo,
    TipoManutencaoRepo,
    UsuarioRepo,
)
from osapp.services import custos, relogio
from osapp.services import status as _status
from osapp.services.auth import Ator, carregar_ator
from osapp.services.erros import (
    ErroConflito,
    ErroNaoEncontrado,
    ErroPermissao,
    ErroValidacao,
)
from osapp.services.permissoes import pode_acessar_filial

logger = logging.getLogger(__name__)

TITULO_MIN = 3
TITULO_MAX = 120
DESCRICAO_MAX = 2000
TEMPO_MAX_MINUTOS = 59_999
BUSCA_MAX = 100
ITENS_POR_PAGINA = 50

TIPO_CRIACAO = "CRIACAO"
TIPO_EDICAO = "EDICAO"
TIPO_STATUS = "STATUS"
TIPO_REALIZADO = "REALIZADO"  # campos preenchidos na conclusão (valor_antigo é sempre nulo)

TOLERANCIA_FUTURO_MINUTOS = 5

ORIGEM_SOLICITACAO = "solicitacao"
ORIGEM_MANUTENCAO = "manutencao"
ORIGENS = (ORIGEM_SOLICITACAO, ORIGEM_MANUTENCAO)
# Urgência (do solicitante) e prioridade (da manutenção) usam a mesma escala.
NIVEIS = ("baixa", "media", "alta", "emergencial")
NOTA_MIN = 5
NOTA_MAX = 500

PENDENCIA_TEMPO = "tempo previsto"
PENDENCIA_VALOR = "custos previstos (pelo menos um item)"
PENDENCIA_TIPO = "tipo de manutenção"
PENDENCIA_PRIORIDADE = "prioridade"
PENDENCIA_EQUIPAMENTO = "equipamento"

CAMPOS_TEXTO = ("titulo", "descricao")
CAMPOS_PREVISTO = ("titulo", "descricao", "tempo_previsto_minutos")  # compatibilidade
CAMPOS_MANUTENCAO = ("tempo_previsto_minutos", "tipo_id", "prioridade")
CAMPOS_SOLICITACAO = ("titulo", "descricao", "urgencia")
CAMPOS_REALIZADO = ("inicio_realizado", "fim_realizado", "descricao_realizado")
CAMPOS_EQUIPAMENTO = ("equipamento_id", "equipamento_outro")
CAMPO_FILIAL = "filial_id"
EQUIPAMENTO_OUTRO_MIN = 3
EQUIPAMENTO_OUTRO_MAX = 120


# --- DTOs -----------------------------------------------------------------------------


@dataclass(frozen=True)
class FilialDTO:
    id: int
    codigo: str
    nome: str


@dataclass(frozen=True)
class TipoDTO:
    id: int
    codigo: str
    nome: str


@dataclass(frozen=True)
class OsResumo:
    """Linha da lista para manutenção e administrador."""

    id: int
    numero: str
    titulo: str
    status: str
    filial_codigo: str
    total_previsto_centavos: int  # calculado dos itens previstos
    criado_em: datetime
    origem: str = ORIGEM_MANUTENCAO
    urgencia: str | None = None
    prioridade: str | None = None
    aberta_em: datetime | None = None
    solicitante: str = ""


@dataclass(frozen=True)
class ResumoSolicitante:
    """Linha da lista para o papel usuario: só campos permitidos."""

    id: int
    numero: str
    titulo: str
    urgencia: str | None
    status: str
    solicitante: str
    filial_codigo: str
    aberta_em: datetime
    inicio_execucao_em: datetime | None
    concluida_em: datetime | None
    cancelada_em: datetime | None


@dataclass(frozen=True)
class PaginaOs:
    itens: tuple  # OsResumo (manutenção, admin) ou ResumoSolicitante (usuario)
    tem_mais: bool


@dataclass(frozen=True)
class EventoDTO:
    data_hora: datetime
    nome_usuario: str
    tipo: str
    campo: str | None
    valor_antigo: str | None
    valor_novo: str | None


@dataclass(frozen=True)
class AcoesOs:
    """O que o ator pode fazer nesta OS. Conveniência para a interface, nunca o controle.

    Calculado pelas mesmas funções que as operações usam para permitir ou recusar.
    """

    pode_editar: bool  # editar_os (campos da manutenção)
    pode_iniciar: bool  # permissão e previsto completo
    pode_desfazer_inicio: bool
    pode_concluir: bool
    pode_editar_realizado: bool
    pode_editar_itens_previstos: bool
    pode_editar_itens_realizados: bool
    pode_cancelar: bool = False
    pode_editar_solicitacao: bool = False  # editar_solicitacao (título, descrição, urgência)


@dataclass(frozen=True)
class AcoesSolicitante:
    pode_editar: bool  # editar_solicitacao
    pode_cancelar: bool
    pode_iniciar: bool
    pode_desfazer_inicio: bool
    pode_concluir: bool


@dataclass(frozen=True)
class OsVisaoSolicitante:
    """Detalhe para o papel usuario. A consulta só lê estas colunas: previsto, realizado,
    custos, equipamento, tipo, prioridade, executor e histórico nem são carregados."""

    id: int
    numero: str
    versao: int
    titulo: str
    descricao: str
    urgencia: str | None
    status: str
    solicitante: str
    filial_codigo: str
    aberta_em: datetime
    inicio_execucao_em: datetime | None
    concluida_em: datetime | None
    cancelada_em: datetime | None
    nota_conclusao: str | None
    acoes: AcoesSolicitante


@dataclass(frozen=True)
class OsDetalhe:
    id: int
    numero: str
    status: str
    versao: int
    titulo: str
    descricao: str
    filial_id: int
    filial_codigo: str
    filial_nome: str
    criado_por_id: int
    criado_por_nome: str
    criado_em: datetime
    atualizado_em: datetime
    tempo_previsto_minutos: int | None
    equipamento_id: int | None
    equipamento_outro: str | None
    equipamento: str | None  # nome do equipamento ou o texto de 'Outro'
    numero_sap: str | None
    executor_id: int | None
    executor_nome: str | None
    inicio_realizado: datetime | None
    fim_realizado: datetime | None
    descricao_realizado: str | None
    concluido_por_id: int | None
    concluido_por_nome: str | None
    # Os dois abaixo são None até a OS ser concluída.
    tempo_realizado_minutos: int | None
    diferenca_tempo_minutos: int | None  # realizado - previsto
    itens: tuple[custos.ItemDTO, ...]  # previstos e realizados, cada um com o total da linha
    resumo_custos: custos.ResumoCustos  # por categoria e geral; sempre calculado
    acoes: AcoesOs
    # Prompt 17: solicitação, classificação e os quatro instantes de status.
    origem: str = ORIGEM_MANUTENCAO
    urgencia: str | None = None  # do solicitante
    prioridade: str | None = None  # da manutenção
    tipo_id: int | None = None
    tipo_nome: str | None = None
    nota_conclusao: str | None = None
    aberta_em: datetime | None = None
    inicio_execucao_em: datetime | None = None
    concluida_em: datetime | None = None
    cancelada_em: datetime | None = None
    cancelada_por_nome: str | None = None
    pendencias_para_iniciar: tuple[str, ...] = ()  # vazio = previsto completo


# --- Validação ------------------------------------------------------------------------


def _validar_titulo(valor: object) -> str:
    if not isinstance(valor, str):
        raise ErroValidacao("titulo", "Informe o título.")
    valor = valor.strip()
    if len(valor) < TITULO_MIN:
        raise ErroValidacao("titulo", f"O título deve ter pelo menos {TITULO_MIN} caracteres.")
    if len(valor) > TITULO_MAX:
        raise ErroValidacao("titulo", f"O título deve ter no máximo {TITULO_MAX} caracteres.")
    return valor


def _validar_texto_longo(campo: str, valor: object) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ErroValidacao(campo, "Informe a descrição.")
    valor = valor.strip()
    if len(valor) > DESCRICAO_MAX:
        raise ErroValidacao(campo, f"A descrição deve ter no máximo {DESCRICAO_MAX} caracteres.")
    return valor


def _validar_tempo(campo: str, valor: object) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ErroValidacao(campo, "Informe um tempo válido.")
    if valor < 1:
        raise ErroValidacao(campo, "O tempo deve ser de pelo menos 1 minuto.")
    if valor > TEMPO_MAX_MINUTOS:
        raise ErroValidacao(campo, "O tempo é maior que o máximo permitido.")
    return valor


def _e_int(valor: object) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def _validar_instante(campo: str, valor: object) -> datetime:
    if not isinstance(valor, datetime) or valor.tzinfo is None or valor.utcoffset() is None:
        raise ErroValidacao(campo, "Informe a data e a hora.")
    return valor.astimezone(UTC)


def _minutos_entre(inicio: datetime, fim: datetime) -> int:
    return int((fim - inicio).total_seconds() // 60)


def _validar_periodo(inicio: datetime, fim: datetime, agora: datetime) -> None:
    if fim <= inicio:
        raise ErroValidacao("fim_realizado", "O fim deve ser depois do início.")
    if fim > agora + timedelta(minutes=TOLERANCIA_FUTURO_MINUTOS):
        raise ErroValidacao("fim_realizado", "O fim não pode estar no futuro.")
    if _minutos_entre(inicio, fim) > TEMPO_MAX_MINUTOS:
        raise ErroValidacao("fim_realizado", "A duração é maior que o máximo permitido.")


def _validar_nivel(campo: str, valor: object, obrigatorio: bool) -> str | None:
    """Urgência ou prioridade: baixa, media, alta ou emergencial."""
    if valor is None and not obrigatorio:
        return None
    if valor not in NIVEIS:
        nome = "a urgência" if campo == "urgencia" else "a prioridade"
        raise ErroValidacao(campo, f"Escolha {nome}: baixa, média, alta ou emergencial.")
    return valor


def _validar_nota(valor: object) -> str:
    """Nota de conclusão para o solicitante: texto simples de 5 a 500 caracteres."""
    if not isinstance(valor, str):
        raise ErroValidacao("nota_conclusao", "Escreva a nota para o solicitante.")
    valor = valor.strip()
    if any(ord(c) < 32 and c not in "\n\t" for c in valor):
        raise ErroValidacao("nota_conclusao", "A nota tem caracteres inválidos.")
    if not NOTA_MIN <= len(valor) <= NOTA_MAX:
        raise ErroValidacao(
            "nota_conclusao", f"A nota deve ter de {NOTA_MIN} a {NOTA_MAX} caracteres."
        )
    return valor


def _validar_tipo(s: Session, valor: object) -> int | None:
    if valor is None:
        return None
    tipo = TipoManutencaoRepo(s).obter(valor) if _e_int(valor) else None
    if tipo is None or not tipo.ativo:
        raise ErroValidacao("tipo_id", "Escolha um tipo de manutenção válido.")
    return tipo.id


# --- Regras de permissão (as mesmas funções alimentam as ações e as verificações) ----
# ``ordem`` pode ser a entidade ou uma visão leve com status, filial_id, origem,
# criado_por_id e executor_id.


def _manutencao_da_filial(ator: Ator, ordem) -> bool:
    return ator.is_manutencao and ator.filial_id == ordem.filial_id


def _solicitante(ator: Ator, ordem) -> bool:
    """Quem abriu a solicitação (só OS de origem 'solicitacao')."""
    return ordem.origem == ORIGEM_SOLICITACAO and ordem.criado_por_id == ator.usuario_id


def _pode_editar(ator: Ator, ordem) -> bool:
    """editar_os: manutenção da filial até a conclusão; administrador sempre.
    OS cancelada: ninguém."""
    if ordem.status == _status.CANCELADA:
        return False
    if ator.is_admin:
        return True
    return _manutencao_da_filial(ator, ordem) and ordem.status != _status.CONCLUIDA


def _pode_editar_solicitacao(ator: Ator, ordem) -> bool:
    """editar_solicitacao: o solicitante enquanto ABERTA; administrador (exceto cancelada)."""
    if ordem.origem != ORIGEM_SOLICITACAO or ordem.status == _status.CANCELADA:
        return False
    if ator.is_admin:
        return True
    return _solicitante(ator, ordem) and ordem.status == _status.ABERTA


def _pode_editar_realizado(ator: Ator, ordem) -> bool:
    return ator.is_admin and _status.encerrado(ordem.status)


def _pode_editar_itens(ator: Ator, ordem, fase: str) -> bool:
    """PREVISTO: quem pode editar_os. REALIZADO: só administrador, depois da conclusão
    (antes disso os itens realizados chegam apenas junto com a conclusão)."""
    if fase == custos.FASE_PREVISTO:
        return _pode_editar(ator, ordem)
    return _pode_editar_realizado(ator, ordem)


def _pode(acao: str, ator: Ator, ordem) -> bool:
    """Permissão para uma transição da tabela de status (sem o previsto completo)."""
    origem, _destino, quem = _status.transicao(acao)
    if ordem.status != origem:
        return False
    if ator.is_admin:
        return True
    if quem == _status.MANUTENCAO_DA_FILIAL:
        return _manutencao_da_filial(ator, ordem)
    if quem == _status.SOMENTE_EXECUTOR:
        return not ator.is_usuario and ordem.executor_id == ator.usuario_id
    if quem == _status.SOMENTE_SOLICITANTE:
        return _solicitante(ator, ordem)
    return False


def pendencias_para_iniciar(ordem: OrdemServico) -> tuple[str, ...]:
    """O que falta no previsto para iniciar a execução (vazio = completo)."""
    faltam = []
    if ordem.tempo_previsto_minutos is None:
        faltam.append(PENDENCIA_TEMPO)
    if not any(i.fase == custos.FASE_PREVISTO for i in ordem.itens):
        faltam.append(PENDENCIA_VALOR)
    if ordem.tipo_id is None:
        faltam.append(PENDENCIA_TIPO)
    if ordem.prioridade is None:
        faltam.append(PENDENCIA_PRIORIDADE)
    if ordem.equipamento_id is None and not ordem.equipamento_outro:
        faltam.append(PENDENCIA_EQUIPAMENTO)
    return tuple(faltam)


def previsto_completo(ordem: OrdemServico) -> bool:
    """Único ponto que decide se o previsto basta para iniciar a execução."""
    return not pendencias_para_iniciar(ordem)


def _acoes(ator: Ator, ordem: OrdemServico) -> AcoesOs:
    return AcoesOs(
        pode_editar=_pode_editar(ator, ordem),
        pode_iniciar=_pode(_status.INICIAR, ator, ordem) and previsto_completo(ordem),
        pode_desfazer_inicio=_pode(_status.DESFAZER_INICIO, ator, ordem),
        pode_concluir=_pode(_status.CONCLUIR, ator, ordem),
        pode_editar_realizado=_pode_editar_realizado(ator, ordem),
        pode_editar_itens_previstos=_pode_editar_itens(ator, ordem, custos.FASE_PREVISTO),
        pode_editar_itens_realizados=_pode_editar_itens(ator, ordem, custos.FASE_REALIZADO),
        pode_cancelar=_pode(_status.CANCELAR, ator, ordem),
        pode_editar_solicitacao=_pode_editar_solicitacao(ator, ordem),
    )


def _acoes_solicitante(ator: Ator, visao) -> AcoesSolicitante:
    # O papel usuario nunca inicia, desfaz ou conclui: _pode já recusa antes de olhar o
    # previsto (que esta visão nem tem).
    return AcoesSolicitante(
        pode_editar=_pode_editar_solicitacao(ator, visao),
        pode_cancelar=_pode(_status.CANCELAR, ator, visao),
        pode_iniciar=_pode(_status.INICIAR, ator, visao),
        pode_desfazer_inicio=_pode(_status.DESFAZER_INICIO, ator, visao),
        pode_concluir=_pode(_status.CONCLUIR, ator, visao),
    )


# --- Auxiliares -----------------------------------------------------------------------


def _negar(ator: Ator, acao: str) -> ErroPermissao:
    logger.warning("Permissão negada: usuario_id=%s ação=%s.", ator.usuario_id, acao)
    return ErroPermissao()


def _carregar_visivel(s: Session, ator: Ator, os_id: object) -> OrdemServico:
    """A OS, se existir e for da filial do ator (ou se o ator for administrador).

    OS de outra filial e OS inexistente levantam o mesmo ErroNaoEncontrado.
    """
    ordem = OrdemServicoRepo(s).obter(os_id) if _e_int(os_id) else None
    if ordem is None or not pode_acessar_filial(ator, ordem.filial_id):
        raise ErroNaoEncontrado()
    return ordem


def _carregar_para_escrita(s: Session, ator: Ator, os_id: object) -> OrdemServico:
    """Como _carregar_visivel; para o papel usuario não carrega relacionamentos (itens,
    equipamento, executor...): só a linha da OS, para gravar."""
    if not ator.is_usuario:
        return _carregar_visivel(s, ator, os_id)
    ordem = OrdemServicoRepo(s).obter_sem_relacoes(os_id) if _e_int(os_id) else None
    if ordem is None or ordem.filial_id != ator.filial_id:
        raise ErroNaoEncontrado()
    return ordem


def _itens_ordenados(ordem: OrdemServico) -> tuple[custos.ItemDTO, ...]:
    ordem_fase = {custos.FASE_PREVISTO: 0, custos.FASE_REALIZADO: 1}
    dtos = [custos.item_dto(item) for item in ordem.itens]
    return tuple(sorted(dtos, key=lambda d: (ordem_fase[d.fase], d.categoria_ordem, d.id)))


def _nome_do_equipamento(ordem: OrdemServico) -> str | None:
    if ordem.equipamento is not None:
        return ordem.equipamento.nome
    return ordem.equipamento_outro


def _detalhe(ordem: OrdemServico, ator: Ator) -> OsDetalhe:
    tempo_realizado = dif_tempo = None
    if (
        _status.encerrado(ordem.status)
        and ordem.inicio_realizado is not None
        and ordem.fim_realizado is not None
    ):
        tempo_realizado = _minutos_entre(ordem.inicio_realizado, ordem.fim_realizado)
        if ordem.tempo_previsto_minutos is not None:
            dif_tempo = tempo_realizado - ordem.tempo_previsto_minutos
    itens = _itens_ordenados(ordem)
    return OsDetalhe(
        id=ordem.id,
        numero=ordem.numero,
        status=ordem.status,
        versao=ordem.versao,
        titulo=ordem.titulo,
        descricao=ordem.descricao,
        filial_id=ordem.filial_id,
        filial_codigo=ordem.filial.codigo,
        filial_nome=ordem.filial.nome,
        criado_por_id=ordem.criado_por_id,
        criado_por_nome=ordem.criado_por.nome,
        criado_em=ordem.criado_em,
        atualizado_em=ordem.atualizado_em,
        tempo_previsto_minutos=ordem.tempo_previsto_minutos,
        equipamento_id=ordem.equipamento_id,
        equipamento_outro=ordem.equipamento_outro,
        equipamento=_nome_do_equipamento(ordem),
        numero_sap=ordem.numero_sap,
        executor_id=ordem.executor_id,
        executor_nome=ordem.executor.nome if ordem.executor else None,
        inicio_realizado=ordem.inicio_realizado,
        fim_realizado=ordem.fim_realizado,
        descricao_realizado=ordem.descricao_realizado,
        concluido_por_id=ordem.concluido_por_id,
        concluido_por_nome=ordem.concluido_por.nome if ordem.concluido_por else None,
        tempo_realizado_minutos=tempo_realizado,
        diferenca_tempo_minutos=dif_tempo,
        itens=itens,
        resumo_custos=custos.calcular_resumo(itens),
        acoes=_acoes(ator, ordem),
        origem=ordem.origem,
        urgencia=ordem.urgencia,
        prioridade=ordem.prioridade,
        tipo_id=ordem.tipo_id,
        tipo_nome=ordem.tipo.nome if ordem.tipo else None,
        nota_conclusao=ordem.nota_conclusao,
        aberta_em=ordem.aberta_em,
        inicio_execucao_em=ordem.inicio_execucao_em,
        concluida_em=ordem.concluida_em,
        cancelada_em=ordem.cancelada_em,
        cancelada_por_nome=ordem.cancelada_por.nome if ordem.cancelada_por else None,
        pendencias_para_iniciar=pendencias_para_iniciar(ordem),
    )


def _visao_solicitante(linha, ator: Ator) -> OsVisaoSolicitante:
    """Linha da consulta de colunas permitidas -> detalhe do papel usuario."""
    leve = SimpleNamespace(**linha, executor_id=None)
    return OsVisaoSolicitante(
        id=linha["id"],
        numero=linha["numero"],
        versao=linha["versao"],
        titulo=linha["titulo"],
        descricao=linha["descricao"],
        urgencia=linha["urgencia"],
        status=linha["status"],
        solicitante=linha["solicitante"],
        filial_codigo=linha["filial_codigo"],
        aberta_em=linha["aberta_em"],
        inicio_execucao_em=linha["inicio_execucao_em"],
        concluida_em=linha["concluida_em"],
        cancelada_em=linha["cancelada_em"],
        nota_conclusao=linha["nota_conclusao"],
        acoes=_acoes_solicitante(ator, leve),
    )


def _resumo_solicitante(linha) -> ResumoSolicitante:
    return ResumoSolicitante(
        id=linha["id"],
        numero=linha["numero"],
        titulo=linha["titulo"],
        urgencia=linha["urgencia"],
        status=linha["status"],
        solicitante=linha["solicitante"],
        filial_codigo=linha["filial_codigo"],
        aberta_em=linha["aberta_em"],
        inicio_execucao_em=linha["inicio_execucao_em"],
        concluida_em=linha["concluida_em"],
        cancelada_em=linha["cancelada_em"],
    )


def _ver(s: Session, ator: Ator, ordem: OrdemServico):
    """O modelo de leitura do papel do ator, com a OS já gravada."""
    s.flush()
    if ator.is_usuario:
        return _visao_solicitante(OrdemServicoRepo(s).visao_solicitante(ordem.id), ator)
    s.refresh(ordem)  # versão nova e relacionamentos (só para manutenção e administrador)
    return _detalhe(ordem, ator)


def registrar_evento(
    s: Session,
    os_id: int,
    usuario_id: int,
    tipo: str,
    data_hora: datetime,
    campo: str | None = None,
    valor_antigo: str | None = None,
    valor_novo: str | None = None,
) -> None:
    """Único ponto que grava em os_eventos, sempre na sessão (transação) da alteração."""
    OsEventoRepo(s).adicionar(
        OsEvento(
            os_id=os_id,
            usuario_id=usuario_id,
            data_hora=data_hora,
            tipo=tipo,
            campo=campo,
            valor_antigo=valor_antigo,
            valor_novo=valor_novo,
        )
    )


def formatar_numero(codigo_filial: str, ano: int, sequencia: int) -> str:
    """Número da OS: '{código da filial}-{ano}-{sequência de 6 dígitos}', ex. 1007-2026-000001."""
    return f"{codigo_filial}-{ano}-{sequencia:06d}"


def _ano_local(instante: datetime) -> int:
    """Ano do número da OS, no fuso da aplicação (OS_TZ)."""
    return instante.astimezone(ZoneInfo(carregar_config().tz)).year


def _validar_equipamento(
    s: Session,
    filial_id: int,
    equipamento_id: object,
    equipamento_outro: object,
    opcional: bool = False,
) -> tuple[int | None, str | None]:
    """No máximo um: equipamento ativo da filial da OS, ou 'Outro' com texto de 3 a 120.
    Com ``opcional``, nenhum dos dois também vale (o previsto completo cobra depois)."""
    tem_id = equipamento_id is not None
    tem_outro = equipamento_outro is not None and (
        not isinstance(equipamento_outro, str) or equipamento_outro.strip() != ""
    )
    if opcional and not tem_id and not tem_outro:
        return None, None
    if tem_id == tem_outro:
        raise ErroValidacao(
            "equipamento_id", "Escolha um equipamento da lista ou informe 'Outro', não os dois."
        )
    if tem_id:
        equipamento = EquipamentoRepo(s).obter(equipamento_id) if _e_int(equipamento_id) else None
        if equipamento is None or equipamento.filial_id != filial_id or not equipamento.ativo:
            raise ErroValidacao("equipamento_id", "Escolha um equipamento ativo desta filial.")
        return equipamento.id, None
    if not isinstance(equipamento_outro, str):
        raise ErroValidacao("equipamento_outro", "Descreva o equipamento.")
    texto = equipamento_outro.strip()
    if not EQUIPAMENTO_OUTRO_MIN <= len(texto) <= EQUIPAMENTO_OUTRO_MAX:
        raise ErroValidacao(
            "equipamento_outro",
            f"Descreva o equipamento com {EQUIPAMENTO_OUTRO_MIN} a {EQUIPAMENTO_OUTRO_MAX} "
            "caracteres.",
        )
    return None, texto


def _gravar_itens(
    s: Session, ordem: OrdemServico, ator: Ator, fase: str, itens: list[tuple], agora: datetime
) -> None:
    """Grava itens já validados, com um evento ITEM_ADICIONADO por item."""
    for categoria, descricao, quantidade, valor in itens:
        item = OsItemCusto(
            os_id=ordem.id,
            fase=fase,
            categoria_id=categoria.id,
            descricao=descricao,
            quantidade=quantidade,
            valor_unitario_centavos=valor,
            criado_em=agora,
            atualizado_em=agora,
        )
        s.add(item)
        s.flush()
        registrar_evento(
            s,
            ordem.id,
            ator.usuario_id,
            custos.TIPO_ITEM_ADICIONADO,
            agora,
            f"item {item.id}",
            None,
            custos.texto_do_item(categoria.nome, descricao, quantidade, valor),
        )


# --- Funções públicas: criação --------------------------------------------------------


def _filial_de_destino(ator: Ator, filial_id: object, acao: str) -> int:
    """Filial travada na do ator; só o administrador escolhe outra."""
    if filial_id is not None and not _e_int(filial_id):
        raise ErroValidacao("filial_id", "Filial inválida.")
    if not ator.is_admin and filial_id is not None and filial_id != ator.filial_id:
        raise _negar(ator, f"{acao} em outra filial")
    return ator.filial_id if filial_id is None else filial_id


def _nova_ordem(s: Session, ator: Ator, filial_id: int, agora: datetime, **campos) -> OrdemServico:
    filial = FilialRepo(s).obter(filial_id)
    if filial is None:
        raise ErroValidacao("filial_id", "Filial não encontrada.")
    ano = _ano_local(agora)
    sequencia = OsSequenciaRepo(s).reservar_proximo(filial.id, ano)
    ordem = OrdemServicoRepo(s).adicionar(
        OrdemServico(
            numero=formatar_numero(filial.codigo, ano, sequencia),
            filial_id=filial.id,
            criado_por_id=ator.usuario_id,
            status=_status.STATUS_INICIAL,
            criado_em=agora,
            atualizado_em=agora,
            aberta_em=agora,
            **campos,
        )
    )
    registrar_evento(s, ordem.id, ator.usuario_id, TIPO_CRIACAO, agora)
    return ordem


def criar_solicitacao(
    ator_id: int, titulo: str, descricao: str, urgencia: str, filial_id: int | None = None
):
    """Solicitação (origem 'solicitacao'), aberta por qualquer papel. Devolve o modelo de
    leitura do papel do ator (OsVisaoSolicitante para usuario)."""
    ator = carregar_ator(ator_id)
    destino = _filial_de_destino(ator, filial_id, "abrir solicitação")
    titulo = _validar_titulo(titulo)
    descricao = _validar_texto_longo("descricao", descricao)
    urgencia = _validar_nivel("urgencia", urgencia, obrigatorio=True)
    try:
        with sessao() as s:
            agora = relogio.agora()
            ordem = _nova_ordem(
                s,
                ator,
                destino,
                agora,
                origem=ORIGEM_SOLICITACAO,
                titulo=titulo,
                descricao=descricao,
                urgencia=urgencia,
            )
            logger.info("Solicitação aberta: os_id=%s usuario_id=%s.", ordem.id, ator.usuario_id)
            return _ver(s, ator, ordem)
    except IntegrityError:
        logger.exception("Número de OS repetido apesar do contador.")
        raise ErroConflito() from None


def criar_os(
    ator_id: int,
    titulo: str,
    descricao: str,
    itens_previstos: list[custos.ItemEntrada] | None = None,
    tempo_previsto_minutos: int | None = None,
    filial_id: int | None = None,
    *,
    equipamento_id: int | None = None,
    equipamento_outro: str | None = None,
    tipo_id: int | None = None,
    prioridade: str | None = None,
) -> OsDetalhe:
    """OS completa (origem 'manutencao'): só manutenção e administrador. Previsto, tipo,
    prioridade e equipamento são opcionais aqui; iniciar exige o previsto completo.
    Um evento CRIACAO e um ITEM_ADICIONADO por item, numa só transação."""
    ator = carregar_ator(ator_id)
    if ator.is_usuario:
        raise _negar(ator, "criar OS completa")
    destino = _filial_de_destino(ator, filial_id, "criar OS")
    titulo = _validar_titulo(titulo)
    descricao = _validar_texto_longo("descricao", descricao)
    tempo = (
        None
        if tempo_previsto_minutos is None
        else _validar_tempo("tempo_previsto_minutos", tempo_previsto_minutos)
    )
    prioridade = _validar_nivel("prioridade", prioridade, obrigatorio=False)
    try:
        with sessao() as s:
            itens = (
                custos.validar_itens_de_entrada(s, itens_previstos, "itens_previstos")
                if itens_previstos
                else []
            )
            eq_id, eq_outro = _validar_equipamento(
                s, destino, equipamento_id, equipamento_outro, opcional=True
            )
            agora = relogio.agora()
            ordem = _nova_ordem(
                s,
                ator,
                destino,
                agora,
                origem=ORIGEM_MANUTENCAO,
                titulo=titulo,
                descricao=descricao,
                tempo_previsto_minutos=tempo,
                equipamento_id=eq_id,
                equipamento_outro=eq_outro,
                tipo_id=_validar_tipo(s, tipo_id),
                prioridade=prioridade,
            )
            _gravar_itens(s, ordem, ator, custos.FASE_PREVISTO, itens, agora)
            s.flush()
            s.refresh(ordem)
            logger.info("OS criada: os_id=%s usuario_id=%s.", ordem.id, ator.usuario_id)
            return _detalhe(ordem, ator)
    except IntegrityError:
        # Rede de segurança: a restrição de unicidade de "numero" recusou. Com o contador
        # travado isso não deveria ocorrer; a transação inteira foi desfeita.
        logger.exception("Número de OS repetido apesar do contador.")
        raise ErroConflito() from None


# --- Funções públicas: leitura --------------------------------------------------------


def obter_os(ator_id: int, os_id: int):
    """OsDetalhe (manutenção, administrador) ou OsVisaoSolicitante (usuario)."""
    ator = carregar_ator(ator_id)
    with sessao() as s:
        if ator.is_usuario:
            linha = OrdemServicoRepo(s).visao_solicitante(os_id) if _e_int(os_id) else None
            if linha is None or linha["filial_id"] != ator.filial_id:
                raise ErroNaoEncontrado()
            return _visao_solicitante(linha, ator)
        return _detalhe(_carregar_visivel(s, ator, os_id), ator)


def listar_os(
    ator_id: int,
    busca: str | None = None,
    status: str | None = None,
    filial_id: int | None = None,
    pagina: int = 1,
    origem: str | None = None,
) -> PaginaOs:
    """Lista paginada. O papel usuario recebe ResumoSolicitante, só da própria filial."""
    ator = carregar_ator(ator_id)
    if filial_id is not None and not _e_int(filial_id):
        raise ErroValidacao("filial_id", "Filial inválida.")
    if ator.is_admin:
        filtro_filial = filial_id  # None = todas as filiais
    elif filial_id is None or filial_id == ator.filial_id:
        filtro_filial = ator.filial_id
    else:
        raise _negar(ator, "listar OS de outra filial")

    if busca is not None and not isinstance(busca, str):
        raise ErroValidacao("busca", "Busca inválida.")
    busca = (busca or "").strip()[:BUSCA_MAX] or None
    if status is not None and not _status.status_conhecido(status):
        raise ErroValidacao("status", "Status inválido.")
    if origem is not None and origem not in ORIGENS:
        raise ErroValidacao("origem", "Origem inválida.")
    if not _e_int(pagina) or pagina < 1:
        raise ErroValidacao("pagina", "Página inválida.")
    limite, deslocamento = ITENS_POR_PAGINA + 1, (pagina - 1) * ITENS_POR_PAGINA

    with sessao() as s:
        repo = OrdemServicoRepo(s)
        if ator.is_usuario:
            linhas = repo.listar_visao_solicitante(
                filtro_filial, status, busca, limite, deslocamento
            )
            itens = tuple(_resumo_solicitante(linha) for linha in linhas[:ITENS_POR_PAGINA])
            return PaginaOs(itens=itens, tem_mais=len(linhas) > ITENS_POR_PAGINA)
        ordens = repo.listar(
            filial_id=filtro_filial,
            status=status,
            busca=busca,
            limite=limite,
            deslocamento=deslocamento,
            origem=origem,
        )
        itens = tuple(
            OsResumo(
                id=o.id,
                numero=o.numero,
                titulo=o.titulo,
                status=o.status,
                filial_codigo=o.filial.codigo,
                total_previsto_centavos=sum(
                    custos.total_da_linha(i.quantidade, i.valor_unitario_centavos)
                    for i in o.itens
                    if i.fase == custos.FASE_PREVISTO
                ),
                criado_em=o.criado_em,
                origem=o.origem,
                urgencia=o.urgencia,
                prioridade=o.prioridade,
                aberta_em=o.aberta_em,
                solicitante=o.criado_por.nome,
            )
            for o in ordens[:ITENS_POR_PAGINA]
        )
        return PaginaOs(itens=itens, tem_mais=len(ordens) > ITENS_POR_PAGINA)


def listar_eventos(ator_id: int, os_id: int) -> list[EventoDTO]:
    """Eventos da OS, do mais antigo para o mais novo. O papel usuario não vê o histórico."""
    ator = carregar_ator(ator_id)
    if ator.is_usuario:
        raise _negar(ator, "ver histórico")
    with sessao() as s:
        ordem = _carregar_visivel(s, ator, os_id)
        return [
            EventoDTO(
                data_hora=e.data_hora,
                nome_usuario=e.usuario.nome,
                tipo=e.tipo,
                campo=e.campo,
                valor_antigo=e.valor_antigo,
                valor_novo=e.valor_novo,
            )
            for e in OsEventoRepo(s).listar_por_os(ordem.id)
        ]


def listar_filiais(ator_id: int) -> list[FilialDTO]:
    """Administrador recebe todas as filiais; os demais, apenas a própria."""
    ator = carregar_ator(ator_id)
    with sessao() as s:
        repo = FilialRepo(s)
        filiais = repo.listar() if ator.is_admin else [repo.obter(ator.filial_id)]
        return [FilialDTO(f.id, f.codigo, f.nome) for f in filiais if f is not None]


def listar_tipos(ator_id: int) -> list[TipoDTO]:
    """Tipos de manutenção ativos (manutenção e administrador)."""
    ator = carregar_ator(ator_id)
    if ator.is_usuario:
        raise _negar(ator, "listar tipos de manutenção")
    with sessao() as s:
        return [TipoDTO(t.id, t.codigo, t.nome) for t in TipoManutencaoRepo(s).listar()]


# --- Escrita: edição, status e conclusão ----------------------------------------------


def _conferir_versao(ordem: OrdemServico, versao: object) -> None:
    if not _e_int(versao) or versao != ordem.versao:
        raise ErroConflito()


def _como_texto(valor: object) -> str | None:
    """Representação em texto gravada no histórico."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.astimezone(UTC).isoformat()
    return str(valor)


def _mudar_status(
    s: Session,
    ator: Ator,
    ordem: OrdemServico,
    acao: str,
    agora: datetime,
    outros_campos: dict[str, object],
) -> None:
    """Aplica uma transição da tabela: campos e evento STATUS, na mesma transação.

    Os instantes de status (aberta_em, inicio_execucao_em, concluida_em, cancelada_em)
    só são gravados aqui e por _nova_ordem, sempre com relogio.agora().
    """
    _origem, destino, _quem = _status.transicao(acao)
    anterior = ordem.status
    ordem.status = destino
    ordem.atualizado_em = agora
    for campo, valor in outros_campos.items():
        setattr(ordem, campo, valor)
    registrar_evento(s, ordem.id, ator.usuario_id, TIPO_STATUS, agora, "status", anterior, destino)


def _registrar_mudancas(s, ator, ordem, mudancas, agora) -> None:
    for campo, texto_antigo, texto_novo in mudancas:
        registrar_evento(
            s, ordem.id, ator.usuario_id, TIPO_EDICAO, agora, campo, texto_antigo, texto_novo
        )


def editar_os(ator_id: int, os_id: int, versao: int, alteracoes: dict) -> OsDetalhe:
    """Campos da manutenção (tempo previsto, tipo, prioridade, equipamento; filial só o
    administrador; título e descrição só em OS de origem 'manutencao'; realizado só o
    administrador em OS concluída). Um evento EDICAO por campo que mudou."""
    ator = carregar_ator(ator_id)
    if ator.is_usuario:
        raise _negar(ator, "editar campos da manutenção")
    try:
        with sessao() as s:
            ordem = _carregar_visivel(s, ator, os_id)
            if not isinstance(alteracoes, dict):
                raise ErroValidacao("alteracoes", "Dados inválidos.")
            if not _pode_editar(ator, ordem):
                raise _negar(ator, "editar OS")
            permitidos = set(CAMPOS_MANUTENCAO) | set(CAMPOS_EQUIPAMENTO)
            if ordem.origem == ORIGEM_MANUTENCAO:
                permitidos.update(CAMPOS_TEXTO)
            if ator.is_admin:
                permitidos.add(CAMPO_FILIAL)
            if _pode_editar_realizado(ator, ordem):
                permitidos.update(CAMPOS_REALIZADO)
            if not set(alteracoes) <= permitidos:
                raise _negar(ator, "editar campo não permitido")
            _conferir_versao(ordem, versao)

            agora = relogio.agora()
            novos: dict[str, object] = {}
            for campo, valor in alteracoes.items():
                if campo == "titulo":
                    novos[campo] = _validar_titulo(valor)
                elif campo in ("descricao", "descricao_realizado"):
                    novos[campo] = _validar_texto_longo(campo, valor)
                elif campo == "tempo_previsto_minutos":
                    novos[campo] = _validar_tempo(campo, valor)
                elif campo == "tipo_id":
                    novos[campo] = _validar_tipo(s, valor)
                elif campo == "prioridade":
                    novos[campo] = _validar_nivel(campo, valor, obrigatorio=False)
                elif campo in ("inicio_realizado", "fim_realizado"):
                    novos[campo] = _validar_instante(campo, valor)
                elif campo == CAMPO_FILIAL:
                    if not _e_int(valor) or FilialRepo(s).obter(valor) is None:
                        raise ErroValidacao(campo, "Filial não encontrada.")
                    novos[campo] = valor
            if set(alteracoes) & {*CAMPOS_EQUIPAMENTO, CAMPO_FILIAL}:
                # Informar um dos dois troca o tipo: escolher da lista apaga o 'Outro' e
                # vice-versa. Mudar a filial exige que o equipamento seja da nova filial.
                if "equipamento_id" in alteracoes or "equipamento_outro" in alteracoes:
                    eq_id = alteracoes.get("equipamento_id")
                    eq_outro = alteracoes.get("equipamento_outro")
                else:
                    eq_id, eq_outro = ordem.equipamento_id, ordem.equipamento_outro
                filial_final = novos.get(CAMPO_FILIAL, ordem.filial_id)
                eq_id, eq_outro = _validar_equipamento(
                    s, filial_final, eq_id, eq_outro, opcional=True
                )
                novos["equipamento_id"], novos["equipamento_outro"] = eq_id, eq_outro
            if "inicio_realizado" in novos or "fim_realizado" in novos:
                _validar_periodo(
                    novos.get("inicio_realizado", ordem.inicio_realizado),
                    novos.get("fim_realizado", ordem.fim_realizado),
                    agora,
                )

            mudancas: list[tuple[str, str | None, str | None]] = []
            for campo, novo in novos.items():
                antigo = getattr(ordem, campo)
                if antigo == novo:
                    continue
                if campo == CAMPO_FILIAL:  # no histórico vai o código da filial, não o id
                    mudancas.append((campo, ordem.filial.codigo, FilialRepo(s).obter(novo).codigo))
                elif campo == "equipamento_id":  # e o nome do equipamento, não o id
                    repo = EquipamentoRepo(s)
                    mudancas.append(
                        (
                            campo,
                            repo.obter(antigo).nome if antigo else None,
                            repo.obter(novo).nome if novo else None,
                        )
                    )
                elif campo == "tipo_id":  # e o nome do tipo
                    repo_tipo = TipoManutencaoRepo(s)
                    mudancas.append(
                        (
                            campo,
                            repo_tipo.obter(antigo).nome if antigo else None,
                            repo_tipo.obter(novo).nome if novo else None,
                        )
                    )
                else:
                    mudancas.append((campo, _como_texto(antigo), _como_texto(novo)))
                setattr(ordem, campo, novo)
            if mudancas:
                ordem.atualizado_em = agora
            # A OS já está toda alterada: é gravada uma vez só, junto com o primeiro evento.
            _registrar_mudancas(s, ator, ordem, mudancas, agora)
            if mudancas:
                s.flush()
                s.refresh(ordem)
                logger.info("OS editada: os_id=%s usuario_id=%s.", ordem.id, ator.usuario_id)
            return _detalhe(ordem, ator)
    except StaleDataError:
        raise ErroConflito() from None


def editar_solicitacao(ator_id: int, os_id: int, versao: int, alteracoes: dict):
    """Título, descrição e urgência de uma solicitação: o solicitante enquanto ABERTA, o
    administrador a qualquer momento (nunca numa cancelada). A manutenção não muda a
    urgência."""
    ator = carregar_ator(ator_id)
    try:
        with sessao() as s:
            ordem = _carregar_para_escrita(s, ator, os_id)
            if not isinstance(alteracoes, dict) or not alteracoes:
                raise ErroValidacao("alteracoes", "Dados inválidos.")
            if not _pode_editar_solicitacao(ator, ordem):
                raise _negar(ator, "editar solicitação")
            if not set(alteracoes) <= set(CAMPOS_SOLICITACAO):
                raise _negar(ator, "editar campo não permitido na solicitação")
            _conferir_versao(ordem, versao)
            novos = {}
            for campo, valor in alteracoes.items():
                if campo == "titulo":
                    novos[campo] = _validar_titulo(valor)
                elif campo == "descricao":
                    novos[campo] = _validar_texto_longo(campo, valor)
                else:
                    novos[campo] = _validar_nivel("urgencia", valor, obrigatorio=True)
            agora = relogio.agora()
            mudancas = []
            for campo, novo in novos.items():
                antigo = getattr(ordem, campo)
                if antigo != novo:
                    mudancas.append((campo, _como_texto(antigo), _como_texto(novo)))
                    setattr(ordem, campo, novo)
            if mudancas:
                ordem.atualizado_em = agora
            _registrar_mudancas(s, ator, ordem, mudancas, agora)
            s.flush()
            if mudancas:
                logger.info(
                    "Solicitação editada: os_id=%s usuario_id=%s.", ordem.id, ator.usuario_id
                )
            return _ver(s, ator, ordem)
    except StaleDataError:
        raise ErroConflito() from None


def iniciar_execucao(ator_id: int, os_id: int, versao: int) -> OsDetalhe:
    """ABERTA -> EM_EXECUCAO: manutenção da filial ou administrador, com o previsto completo.
    Grava executor e inicio_execucao_em."""
    ator = carregar_ator(ator_id)
    try:
        with sessao() as s:
            ordem = _carregar_visivel(s, ator, os_id)
            if not _pode(_status.INICIAR, ator, ordem):
                raise _negar(ator, f"iniciar OS em status {ordem.status}")
            _conferir_versao(ordem, versao)
            faltam = pendencias_para_iniciar(ordem)
            if faltam:
                raise ErroValidacao(
                    "previsto", "Para iniciar a execução, preencha: " + ", ".join(faltam) + "."
                )
            agora = relogio.agora()
            _mudar_status(
                s,
                ator,
                ordem,
                _status.INICIAR,
                agora,
                {"executor_id": ator.usuario_id, "inicio_execucao_em": agora},
            )
            s.flush()
            s.refresh(ordem)
            logger.info("OS iniciada: os_id=%s usuario_id=%s.", ordem.id, ator.usuario_id)
            return _detalhe(ordem, ator)
    except StaleDataError:
        raise ErroConflito() from None


def desfazer_inicio(ator_id: int, os_id: int, versao: int) -> OsDetalhe:
    """EM_EXECUCAO -> ABERTA: o executor ou o administrador. Apaga executor e
    inicio_execucao_em (o tempo de resposta conta do início verdadeiro); o histórico fica."""
    ator = carregar_ator(ator_id)
    try:
        with sessao() as s:
            ordem = _carregar_visivel(s, ator, os_id)
            if not _pode(_status.DESFAZER_INICIO, ator, ordem):
                raise _negar(ator, f"desfazer início em status {ordem.status}")
            _conferir_versao(ordem, versao)
            _mudar_status(
                s,
                ator,
                ordem,
                _status.DESFAZER_INICIO,
                relogio.agora(),
                {"executor_id": None, "inicio_execucao_em": None},
            )
            s.flush()
            s.refresh(ordem)
            logger.info("Início desfeito: os_id=%s usuario_id=%s.", ordem.id, ator.usuario_id)
            return _detalhe(ordem, ator)
    except StaleDataError:
        raise ErroConflito() from None


def concluir_os(
    ator_id: int,
    os_id: int,
    versao: int,
    itens_realizados: list[custos.ItemEntrada],
    inicio_realizado: datetime,
    fim_realizado: datetime,
    descricao_realizado: str,
    nota_conclusao: str,
) -> OsDetalhe:
    """EM_EXECUCAO -> CONCLUIDA: o executor ou o administrador, com o realizado (itens,
    início, fim, descrição) e a nota para o solicitante. Grava concluida_em."""
    ator = carregar_ator(ator_id)
    try:
        with sessao() as s:
            ordem = _carregar_visivel(s, ator, os_id)
            if not _pode(_status.CONCLUIR, ator, ordem):
                raise _negar(ator, f"concluir OS em status {ordem.status}")
            _conferir_versao(ordem, versao)
            agora = relogio.agora()
            itens = custos.validar_itens_de_entrada(s, itens_realizados, "itens_realizados")
            realizado = {
                "inicio_realizado": _validar_instante("inicio_realizado", inicio_realizado),
                "fim_realizado": _validar_instante("fim_realizado", fim_realizado),
                "descricao_realizado": _validar_texto_longo(
                    "descricao_realizado", descricao_realizado
                ),
            }
            _validar_periodo(realizado["inicio_realizado"], realizado["fim_realizado"], agora)
            nota = _validar_nota(nota_conclusao)

            _mudar_status(
                s,
                ator,
                ordem,
                _status.CONCLUIR,
                agora,
                {
                    "concluido_por_id": ator.usuario_id,
                    "concluida_em": agora,
                    "nota_conclusao": nota,
                    **realizado,
                },
            )
            for campo, valor in (*realizado.items(), ("nota_conclusao", nota)):
                registrar_evento(
                    s,
                    ordem.id,
                    ator.usuario_id,
                    TIPO_REALIZADO,
                    agora,
                    campo,
                    None,
                    _como_texto(valor),
                )
            _gravar_itens(s, ordem, ator, custos.FASE_REALIZADO, itens, agora)
            s.flush()
            s.refresh(ordem)
            logger.info("OS concluída: os_id=%s usuario_id=%s.", ordem.id, ator.usuario_id)
            return _detalhe(ordem, ator)
    except StaleDataError:
        raise ErroConflito() from None


def cancelar(ator_id: int, os_id: int, versao: int):
    """ABERTA -> CANCELADA: o solicitante (na própria solicitação) ou o administrador.
    Grava cancelada_em e cancelada_por_id. Devolve o modelo de leitura do papel."""
    ator = carregar_ator(ator_id)
    try:
        with sessao() as s:
            ordem = _carregar_para_escrita(s, ator, os_id)
            if not _pode(_status.CANCELAR, ator, ordem):
                raise _negar(ator, f"cancelar OS em status {ordem.status}")
            _conferir_versao(ordem, versao)
            agora = relogio.agora()
            _mudar_status(
                s,
                ator,
                ordem,
                _status.CANCELAR,
                agora,
                {"cancelada_em": agora, "cancelada_por_id": ator.usuario_id},
            )
            s.flush()
            logger.info("OS cancelada: os_id=%s usuario_id=%s.", ordem.id, ator.usuario_id)
            return _ver(s, ator, ordem)
    except StaleDataError:
        raise ErroConflito() from None


# --- Itens de custo (chamado por services/custos.py) ----------------------------------


def _marcar_alterada(ordem: OrdemServico, agora: datetime) -> None:
    """Força a gravação da OS (e o incremento de ``versao``) mesmo se ``atualizado_em``
    não mudar de valor (duas alterações no mesmo instante do relógio)."""
    ordem.atualizado_em = agora
    flag_modified(ordem, "atualizado_em")


def _alterar_itens(
    ator_id: int,
    os_id: int,
    versao: int,
    fase: str | None,
    acao: tuple[str, int | None],
    dados: dict,
) -> OsDetalhe:
    """Inclui, altera ou remove um item, com as regras de visibilidade, permissão,
    versão, mínimo de itens e histórico. Cada mudança incrementa a versão da OS."""
    ator = carregar_ator(ator_id)
    operacao, item_id = acao
    try:
        with sessao() as s:
            ordem = _carregar_visivel(s, ator, os_id)
            item = None
            if operacao == "adicionar":
                fase = custos.validar_fase(fase)
            else:
                item = s.get(OsItemCusto, item_id) if _e_int(item_id) else None
                if item is None or item.os_id != ordem.id:
                    raise ErroNaoEncontrado()
                fase = item.fase
            if not _pode_editar_itens(ator, ordem, fase):
                raise _negar(ator, f"{operacao} item {fase}")
            if operacao == "editar" and (
                not isinstance(dados, dict) or not set(dados) <= set(custos.CAMPOS_DO_ITEM)
            ):
                raise _negar(ator, "editar campo de item não permitido")
            _conferir_versao(ordem, versao)
            agora = relogio.agora()
            da_fase = [i for i in ordem.itens if i.fase == fase]

            if operacao == "adicionar":
                if len(da_fase) >= custos.ITENS_MAX_POR_FASE:
                    raise ErroValidacao(
                        "itens", f"No máximo {custos.ITENS_MAX_POR_FASE} itens por fase."
                    )
                entrada = custos.ItemEntrada(**dados)
                validado = custos.validar_itens_de_entrada(s, [entrada], "item")
                _marcar_alterada(ordem, agora)
                _gravar_itens(s, ordem, ator, fase, validado, agora)

            elif operacao == "editar":
                novos = {}
                for campo, valor in dados.items():
                    if campo == "categoria_id":
                        novos[campo] = custos.categoria_ativa(s, valor).id
                    elif campo == "descricao":
                        novos[campo] = custos.validar_descricao(valor)
                    elif campo == "quantidade":
                        novos[campo] = custos.validar_quantidade(valor)
                    else:
                        novos[campo] = custos.validar_valor_unitario(valor)
                mudancas = [
                    (c, getattr(item, c), v) for c, v in novos.items() if getattr(item, c) != v
                ]
                if not mudancas:
                    return _detalhe(ordem, ator)
                nomes = {c.id: c.nome for c in CategoriaCustoRepo(s).listar(so_ativas=False)}
                _marcar_alterada(ordem, agora)
                for campo, _antigo, novo in mudancas:
                    setattr(item, campo, novo)
                item.atualizado_em = agora
                s.flush()
                for campo, antigo, novo in mudancas:
                    registrar_evento(
                        s,
                        ordem.id,
                        ator.usuario_id,
                        custos.TIPO_ITEM_ALTERADO,
                        agora,
                        f"item {item.id} - {custos.CAMPOS_DO_ITEM[campo]}",
                        custos.texto_do_campo(campo, antigo, nomes),
                        custos.texto_do_campo(campo, novo, nomes),
                    )

            else:  # remover
                # Previsto em OS ABERTA pode ficar vazio (iniciar cobra o previsto completo);
                # depois disso, e no realizado, a fase mantém pelo menos um item.
                livre = fase == custos.FASE_PREVISTO and ordem.status == _status.ABERTA
                if not livre and len(da_fase) <= 1:
                    raise ErroValidacao(
                        "itens", "A Ordem de Serviço precisa de pelo menos um item nesta fase."
                    )
                texto = custos.texto_do_item(
                    item.categoria.nome,
                    item.descricao,
                    item.quantidade,
                    item.valor_unitario_centavos,
                )
                _marcar_alterada(ordem, agora)
                registrar_evento(
                    s,
                    ordem.id,
                    ator.usuario_id,
                    custos.TIPO_ITEM_REMOVIDO,
                    agora,
                    f"item {item.id}",
                    texto,
                    None,
                )
                s.delete(item)

            s.flush()
            s.refresh(ordem)
            logger.info(
                "Item de custo (%s): os_id=%s usuario_id=%s.", operacao, ordem.id, ator.usuario_id
            )
            return _detalhe(ordem, ator)
    except StaleDataError:
        raise ErroConflito() from None


# --- Manutenção de dados (CLI) --------------------------------------------------------


@dataclass(frozen=True)
class Reclassificacao:
    numero: str
    origem_atual: str
    origem_nova: str
    aplicada: bool


def reclassificar_origem(
    login_responsavel: str, numero: str, origem: str, aplicar: bool = False
) -> Reclassificacao:
    """Muda a origem de uma OS antiga (solicitacao | manutencao). Só administrador ativo.

    Sem ``aplicar`` só mostra o que mudaria. Aplicado: um evento EDICAO no histórico.
    """
    if origem not in ORIGENS:
        raise ErroValidacao("origem", "Origem inválida. Use solicitacao ou manutencao.")
    if not isinstance(numero, str) or not numero.strip():
        raise ErroValidacao("numero", "Informe o número da OS.")
    try:
        with sessao() as s:
            responsavel = (
                UsuarioRepo(s).obter_por_login(login_responsavel.strip())
                if isinstance(login_responsavel, str)
                else None
            )
            if responsavel is None or not responsavel.ativo or responsavel.papel != "admin":
                raise ErroPermissao()
            ordem = OrdemServicoRepo(s).obter_por_numero(numero.strip())
            if ordem is None:
                raise ErroNaoEncontrado()
            atual = ordem.origem
            if not aplicar or atual == origem:
                return Reclassificacao(ordem.numero, atual, origem, False)
            agora = relogio.agora()
            ordem.origem = origem
            ordem.atualizado_em = agora
            registrar_evento(
                s, ordem.id, responsavel.id, TIPO_EDICAO, agora, "origem", atual, origem
            )
            logger.info("Origem reclassificada: os_id=%s usuario_id=%s.", ordem.id, responsavel.id)
            return Reclassificacao(ordem.numero, atual, origem, True)
    except StaleDataError:
        raise ErroConflito() from None
