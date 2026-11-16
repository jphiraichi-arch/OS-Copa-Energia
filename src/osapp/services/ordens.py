"""Serviço de ordens de serviço.

Toda função pública recebe ``ator_id`` como primeiro argumento, começa por
``carregar_ator``, abre a própria sessão e devolve dataclasses congeladas (nunca
objetos do ORM). As regras de filial e de papel são aplicadas aqui.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

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
