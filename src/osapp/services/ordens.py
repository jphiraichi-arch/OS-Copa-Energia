"""Serviço de ordens de serviço.

Toda função pública recebe ``ator_id`` como primeiro argumento, começa por
``carregar_ator``, abre a própria sessão e devolve dataclasses congeladas (nunca
objetos do ORM). As regras de filial e de papel são aplicadas aqui.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from osapp.config import carregar_config
from osapp.db import sessao
from osapp.models import OrdemServico, OsEvento
from osapp.repositories import FilialRepo, OrdemServicoRepo, OsEventoRepo
from osapp.services import relogio
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
VALOR_MAX_CENTAVOS = 9_999_999_999
TEMPO_MAX_MINUTOS = 59_999
BUSCA_MAX = 100
ITENS_POR_PAGINA = 50
REPETICOES_DE_NUMERO = 3

TIPO_CRIACAO = "CRIACAO"
TIPO_EDICAO = "EDICAO"
TIPO_STATUS = "STATUS"
TIPO_REALIZADO = "REALIZADO"  # campos preenchidos na conclusão (valor_antigo é sempre nulo)

TOLERANCIA_FUTURO_MINUTOS = 5

CAMPOS_PREVISTO = ("titulo", "descricao", "valor_previsto_centavos", "tempo_previsto_minutos")
CAMPOS_REALIZADO = (
    "valor_realizado_centavos",
    "inicio_realizado",
    "fim_realizado",
    "descricao_realizado",
)
CAMPO_FILIAL = "filial_id"


# --- DTOs -----------------------------------------------------------------------------


@dataclass(frozen=True)
class FilialDTO:
    id: int
    codigo: str
    nome: str


@dataclass(frozen=True)
class OsResumo:
    id: int
    numero: str
    titulo: str
    status: str
    filial_codigo: str
    valor_previsto_centavos: int
    criado_em: datetime


@dataclass(frozen=True)
class PaginaOs:
    itens: tuple[OsResumo, ...]
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
    """O que o ator pode fazer nesta OS. Conveniência para a interface, nunca o controle."""

    pode_editar: bool
    pode_iniciar: bool
    pode_desfazer_inicio: bool
    pode_concluir: bool
    pode_editar_realizado: bool


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
    valor_previsto_centavos: int
    tempo_previsto_minutos: int
    executor_id: int | None
    executor_nome: str | None
    iniciado_em: datetime | None
    valor_realizado_centavos: int | None
    inicio_realizado: datetime | None
    fim_realizado: datetime | None
    descricao_realizado: str | None
    concluido_por_id: int | None
    concluido_por_nome: str | None
    concluido_em: datetime | None
    # Os quatro abaixo são None até a OS ser concluída.
    tempo_realizado_minutos: int | None
    diferenca_valor_centavos: int | None  # realizado - previsto
    diferenca_valor_percentual: float | None  # None quando o valor previsto é 0
    diferenca_tempo_minutos: int | None  # realizado - previsto
    acoes: AcoesOs


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


def _validar_valor(campo: str, valor: object) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ErroValidacao(campo, "Informe um valor válido.")
    if valor < 0:
        raise ErroValidacao(campo, "O valor não pode ser negativo.")
    if valor > VALOR_MAX_CENTAVOS:
        raise ErroValidacao(campo, "O valor é maior que o máximo permitido.")
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


# --- Regras de permissão (as mesmas funções alimentam AcoesOs e as verificações) -----


def _pode_editar(ator: Ator, ordem: OrdemServico) -> bool:
    if _status.encerrado(ordem.status):
        return ator.is_admin
    return ator.is_admin or ordem.criado_por_id == ator.usuario_id


def _pode_editar_realizado(ator: Ator, ordem: OrdemServico) -> bool:
    return ator.is_admin and _status.encerrado(ordem.status)


def _pode_transicionar(ator: Ator, ordem: OrdemServico, destino: str) -> bool:
    quem = _status.quem_pode_transicionar(ordem.status, destino)
    if quem is None or not pode_acessar_filial(ator, ordem.filial_id):
        return False
    if ator.is_admin or quem == _status.QUALQUER_USUARIO_DA_FILIAL:
        return True
    if quem == _status.SOMENTE_EXECUTOR:
        return ordem.executor_id == ator.usuario_id
    return False


def _acoes(ator: Ator, ordem: OrdemServico) -> AcoesOs:
    return AcoesOs(
        pode_editar=_pode_editar(ator, ordem),
        pode_iniciar=_pode_transicionar(ator, ordem, _status.EM_EXECUCAO),
        pode_desfazer_inicio=_pode_transicionar(ator, ordem, _status.ABERTA),
        pode_concluir=_pode_transicionar(ator, ordem, _status.CONCLUIDA),
        pode_editar_realizado=_pode_editar_realizado(ator, ordem),
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


def _detalhe(ordem: OrdemServico, ator: Ator) -> OsDetalhe:
    tempo_realizado = dif_valor = dif_percentual = dif_tempo = None
    if (
        _status.encerrado(ordem.status)
        and ordem.valor_realizado_centavos is not None
        and ordem.inicio_realizado is not None
        and ordem.fim_realizado is not None
    ):
        tempo_realizado = _minutos_entre(ordem.inicio_realizado, ordem.fim_realizado)
        dif_valor = ordem.valor_realizado_centavos - ordem.valor_previsto_centavos
        if ordem.valor_previsto_centavos != 0:
            dif_percentual = round(dif_valor * 100 / ordem.valor_previsto_centavos, 2)
        dif_tempo = tempo_realizado - ordem.tempo_previsto_minutos
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
        valor_previsto_centavos=ordem.valor_previsto_centavos,
        tempo_previsto_minutos=ordem.tempo_previsto_minutos,
        executor_id=ordem.executor_id,
        executor_nome=ordem.executor.nome if ordem.executor else None,
        iniciado_em=ordem.iniciado_em,
        valor_realizado_centavos=ordem.valor_realizado_centavos,
        inicio_realizado=ordem.inicio_realizado,
        fim_realizado=ordem.fim_realizado,
        descricao_realizado=ordem.descricao_realizado,
        concluido_por_id=ordem.concluido_por_id,
        concluido_por_nome=ordem.concluido_por.nome if ordem.concluido_por else None,
        concluido_em=ordem.concluido_em,
        tempo_realizado_minutos=tempo_realizado,
        diferenca_valor_centavos=dif_valor,
        diferenca_valor_percentual=dif_percentual,
        diferenca_tempo_minutos=dif_tempo,
        acoes=_acoes(ator, ordem),
    )


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


def _ano_local(instante: datetime) -> int:
    """Ano do número da OS, no fuso da aplicação (OS_TZ)."""
    return instante.astimezone(ZoneInfo(carregar_config().tz)).year


# --- Funções públicas -----------------------------------------------------------------


def criar_os(
    ator_id: int,
    titulo: str,
    descricao: str,
    valor_previsto_centavos: int,
    tempo_previsto_minutos: int,
    filial_id: int | None = None,
) -> OsDetalhe:
    ator = carregar_ator(ator_id)
    if filial_id is not None and not _e_int(filial_id):
        raise ErroValidacao("filial_id", "Filial inválida.")
    if not ator.is_admin and filial_id is not None and filial_id != ator.filial_id:
        raise _negar(ator, "criar OS em outra filial")
    filial_destino = ator.filial_id if filial_id is None else filial_id

    titulo = _validar_titulo(titulo)
    descricao = _validar_texto_longo("descricao", descricao)
    valor = _validar_valor("valor_previsto_centavos", valor_previsto_centavos)
    tempo = _validar_tempo("tempo_previsto_minutos", tempo_previsto_minutos)

    for _tentativa in range(1 + REPETICOES_DE_NUMERO):
        try:
            with sessao() as s:
                if FilialRepo(s).obter(filial_destino) is None:
                    raise ErroValidacao("filial_id", "Filial não encontrada.")
                agora = relogio.agora()
                repo = OrdemServicoRepo(s)
                ordem = repo.adicionar(
                    OrdemServico(
                        numero=repo.proximo_numero(_ano_local(agora)),
                        filial_id=filial_destino,
                        criado_por_id=ator.usuario_id,
                        titulo=titulo,
                        descricao=descricao,
                        status=_status.STATUS_INICIAL,
                        valor_previsto_centavos=valor,
                        tempo_previsto_minutos=tempo,
                        criado_em=agora,
                        atualizado_em=agora,
                    )
                )
                registrar_evento(s, ordem.id, ator.usuario_id, TIPO_CRIACAO, agora)
                logger.info("OS criada: os_id=%s usuario_id=%s.", ordem.id, ator.usuario_id)
                return _detalhe(ordem, ator)
        except IntegrityError:
            # Outro processo usou o mesmo número; a transação foi desfeita. Tenta de novo.
            logger.info("Conflito ao numerar a OS; nova tentativa.")
    logger.error("Não foi possível numerar a OS após %s tentativas.", 1 + REPETICOES_DE_NUMERO)
    raise ErroConflito()


def obter_os(ator_id: int, os_id: int) -> OsDetalhe:
    ator = carregar_ator(ator_id)
    with sessao() as s:
        return _detalhe(_carregar_visivel(s, ator, os_id), ator)


def listar_os(
    ator_id: int,
    busca: str | None = None,
    status: str | None = None,
    filial_id: int | None = None,
    pagina: int = 1,
) -> PaginaOs:
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
    if not _e_int(pagina) or pagina < 1:
        raise ErroValidacao("pagina", "Página inválida.")

    with sessao() as s:
        ordens = OrdemServicoRepo(s).listar(
            filial_id=filtro_filial,
            status=status,
            busca=busca,
            limite=ITENS_POR_PAGINA + 1,
            deslocamento=(pagina - 1) * ITENS_POR_PAGINA,
        )
        itens = tuple(
            OsResumo(
                id=o.id,
                numero=o.numero,
                titulo=o.titulo,
                status=o.status,
                filial_codigo=o.filial.codigo,
                valor_previsto_centavos=o.valor_previsto_centavos,
                criado_em=o.criado_em,
            )
            for o in ordens[:ITENS_POR_PAGINA]
        )
        return PaginaOs(itens=itens, tem_mais=len(ordens) > ITENS_POR_PAGINA)


def listar_eventos(ator_id: int, os_id: int) -> list[EventoDTO]:
    """Eventos da OS, do mais antigo para o mais novo. Mesma visibilidade de obter_os."""
    ator = carregar_ator(ator_id)
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
    versao: object,
    destino: str,
    agora: datetime,
    outros_campos: dict[str, object],
) -> None:
    """Aplica uma transição da tabela: permissão, versão, campos e evento STATUS.

    Todos os campos da OS são alterados antes do primeiro evento, para que a OS seja
    gravada uma única vez na transação (um só incremento de ``versao``).
    """
    if not _pode_transicionar(ator, ordem, destino):
        raise _negar(ator, f"mudar status de {ordem.status} para {destino}")
    _conferir_versao(ordem, versao)
    anterior = ordem.status
    ordem.status = destino
    ordem.atualizado_em = agora
    for campo, valor in outros_campos.items():
        setattr(ordem, campo, valor)
    registrar_evento(s, ordem.id, ator.usuario_id, TIPO_STATUS, agora, "status", anterior, destino)


def editar_os(ator_id: int, os_id: int, versao: int, alteracoes: dict) -> OsDetalhe:
    """Altera campos da OS. Grava um evento EDICAO por campo que realmente mudou."""
    ator = carregar_ator(ator_id)
    try:
        with sessao() as s:
            ordem = _carregar_visivel(s, ator, os_id)
            if not isinstance(alteracoes, dict):
                raise ErroValidacao("alteracoes", "Dados inválidos.")
            if not _pode_editar(ator, ordem):
                raise _negar(ator, "editar OS")
            permitidos = set(CAMPOS_PREVISTO)
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
                elif campo in ("valor_previsto_centavos", "valor_realizado_centavos"):
                    novos[campo] = _validar_valor(campo, valor)
                elif campo == "tempo_previsto_minutos":
                    novos[campo] = _validar_tempo(campo, valor)
                elif campo in ("inicio_realizado", "fim_realizado"):
                    novos[campo] = _validar_instante(campo, valor)
                elif campo == CAMPO_FILIAL:
                    if not _e_int(valor) or FilialRepo(s).obter(valor) is None:
                        raise ErroValidacao(campo, "Filial não encontrada.")
                    novos[campo] = valor
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
                else:
                    mudancas.append((campo, _como_texto(antigo), _como_texto(novo)))
                setattr(ordem, campo, novo)
            houve_mudanca = bool(mudancas)
            if houve_mudanca:
                ordem.atualizado_em = agora
            # A OS já está toda alterada: é gravada uma vez só, junto com o primeiro evento.
            for campo, texto_antigo, texto_novo in mudancas:
                registrar_evento(
                    s,
                    ordem.id,
                    ator.usuario_id,
                    TIPO_EDICAO,
                    agora,
                    campo,
                    texto_antigo,
                    texto_novo,
                )
            if houve_mudanca:
                s.flush()
                s.refresh(ordem)
                logger.info("OS editada: os_id=%s usuario_id=%s.", ordem.id, ator.usuario_id)
            return _detalhe(ordem, ator)
    except StaleDataError:
        raise ErroConflito() from None


def iniciar_execucao(ator_id: int, os_id: int, versao: int) -> OsDetalhe:
    ator = carregar_ator(ator_id)
    try:
        with sessao() as s:
            ordem = _carregar_visivel(s, ator, os_id)
            agora = relogio.agora()
            _mudar_status(
                s,
                ator,
                ordem,
                versao,
                _status.EM_EXECUCAO,
                agora,
                {"executor_id": ator.usuario_id, "iniciado_em": agora},
            )
            s.flush()
            s.refresh(ordem)
            logger.info("OS iniciada: os_id=%s usuario_id=%s.", ordem.id, ator.usuario_id)
            return _detalhe(ordem, ator)
    except StaleDataError:
        raise ErroConflito() from None


def desfazer_inicio(ator_id: int, os_id: int, versao: int) -> OsDetalhe:
    ator = carregar_ator(ator_id)
    try:
        with sessao() as s:
            ordem = _carregar_visivel(s, ator, os_id)
            _mudar_status(
                s,
                ator,
                ordem,
                versao,
                _status.ABERTA,
                relogio.agora(),
                {"executor_id": None, "iniciado_em": None},
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
    valor_realizado_centavos: int,
    inicio_realizado: datetime,
    fim_realizado: datetime,
    descricao_realizado: str,
) -> OsDetalhe:
    ator = carregar_ator(ator_id)
    try:
        with sessao() as s:
            ordem = _carregar_visivel(s, ator, os_id)
            if not _pode_transicionar(ator, ordem, _status.CONCLUIDA):
                raise _negar(ator, f"concluir OS em status {ordem.status}")
            _conferir_versao(ordem, versao)
            agora = relogio.agora()
            realizado = {
                "valor_realizado_centavos": _validar_valor(
                    "valor_realizado_centavos", valor_realizado_centavos
                ),
                "inicio_realizado": _validar_instante("inicio_realizado", inicio_realizado),
                "fim_realizado": _validar_instante("fim_realizado", fim_realizado),
                "descricao_realizado": _validar_texto_longo(
                    "descricao_realizado", descricao_realizado
                ),
            }
            _validar_periodo(realizado["inicio_realizado"], realizado["fim_realizado"], agora)

            _mudar_status(
                s,
                ator,
                ordem,
                versao,
                _status.CONCLUIDA,
                agora,
                {"concluido_por_id": ator.usuario_id, "concluido_em": agora, **realizado},
            )
            for campo, valor in realizado.items():
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
            s.flush()
            s.refresh(ordem)
            logger.info("OS concluída: os_id=%s usuario_id=%s.", ordem.id, ator.usuario_id)
            return _detalhe(ordem, ator)
    except StaleDataError:
        raise ErroConflito() from None
