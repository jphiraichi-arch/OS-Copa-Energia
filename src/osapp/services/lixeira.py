"""Lixeira (prompt 24): exclusão lógica e restauração de Ordens de Serviço.

Regras (decididas aqui, nunca na interface):
- só o administrador exclui, restaura, lista e abre as ordens excluídas; os demais
  recebem ErroPermissao;
- excluir exige um motivo de 10 a 500 caracteres (aparado); grava excluida_em
  (relogio.agora()), excluida_por_id e motivo_exclusao e o evento EXCLUSAO com o motivo,
  na mesma transação; restaurar limpa os três e grava RESTAURACAO;
- vale em qualquer status. Enquanto excluída, a ordem some de todas as consultas (filtro
  central em models/ordem_servico.py): ninguém a edita, muda o status ou os itens até
  ser restaurada. O número nunca é reutilizado (o contador de numeração nunca volta).
- não há exclusão física: nenhum código emite DELETE em ordens_servico.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import datetime

from sqlalchemy.orm.exc import StaleDataError

from osapp.db import sessao
from osapp.repositories import OrdemServicoRepo, OsEventoRepo
from osapp.services import ordens, relogio
from osapp.services.auth import Ator, carregar_ator
from osapp.services.erros import ErroConflito, ErroNaoEncontrado, ErroPermissao, ErroValidacao
from osapp.services.permissoes import pode_usar_lixeira

logger = logging.getLogger(__name__)

MOTIVO_MIN = 10
MOTIVO_MAX = 500
POR_PAGINA = 50
NENHUMA_ACAO = ordens.AcoesOs(
    pode_editar=False,
    pode_iniciar=False,
    pode_desfazer_inicio=False,
    pode_concluir=False,
    pode_editar_realizado=False,
    pode_editar_itens_previstos=False,
    pode_editar_itens_realizados=False,
    pode_cancelar=False,
    pode_editar_solicitacao=False,
)


@dataclass(frozen=True)
class ItemLixeira:
    id: int
    numero: str
    titulo: str
    status: str  # o status no momento da exclusão (não muda enquanto excluída)
    filial_codigo: str
    excluida_em: datetime
    excluida_por_nome: str
    motivo: str


@dataclass(frozen=True)
class PaginaLixeira:
    itens: tuple[ItemLixeira, ...]
    tem_mais: bool


@dataclass(frozen=True)
class OsExcluida:
    """Detalhe só de leitura de uma ordem excluída (nenhuma ação permitida)."""

    os: ordens.OsDetalhe
    eventos: tuple[ordens.EventoDTO, ...]
    excluida_em: datetime
    excluida_por_nome: str
    motivo: str


@dataclass(frozen=True)
class ResultadoLixeira:
    id: int
    numero: str
    versao: int


def _exigir_admin(ator: Ator, acao: str) -> None:
    if not pode_usar_lixeira(ator):
        logger.warning("Permissão negada: usuario_id=%s ação=%s.", ator.usuario_id, acao)
        raise ErroPermissao()


def validar_motivo(valor: object) -> str:
    if not isinstance(valor, str):
        raise ErroValidacao("motivo", "Informe o motivo da exclusão.")
    motivo = valor.strip()
    if len(motivo) < MOTIVO_MIN:
        raise ErroValidacao("motivo", f"O motivo deve ter pelo menos {MOTIVO_MIN} caracteres.")
    if len(motivo) > MOTIVO_MAX:
        raise ErroValidacao("motivo", f"O motivo deve ter no máximo {MOTIVO_MAX} caracteres.")
    return motivo


def _item(o) -> ItemLixeira:
    return ItemLixeira(
        id=o.id,
        numero=o.numero,
        titulo=o.titulo,
        status=o.status,
        filial_codigo=o.filial.codigo,
        excluida_em=o.excluida_em,
        excluida_por_nome=o.excluida_por.nome if o.excluida_por else "-",
        motivo=o.motivo_exclusao,
    )


def excluir_os(ator_id: int, os_id: int, versao: int, motivo: str) -> ResultadoLixeira:
    """Manda a ordem para a lixeira (some para todos, administrador incluído)."""
    ator = carregar_ator(ator_id)
    _exigir_admin(ator, "excluir OS")
    motivo = validar_motivo(motivo)
    try:
        with sessao() as s:
            ordem = OrdemServicoRepo(s).obter(os_id) if ordens._e_int(os_id) else None
            if ordem is None:  # inexistente ou já excluída
                raise ErroNaoEncontrado()
            ordens._conferir_versao(ordem, versao)
            agora = relogio.agora()
            ordem.excluida_em = agora
            ordem.excluida_por_id = ator.usuario_id
            ordem.motivo_exclusao = motivo
            ordem.atualizado_em = agora
            ordens.registrar_evento(
                s,
                ordem.id,
                ator.usuario_id,
                ordens.TIPO_EXCLUSAO,
                agora,
                "exclusao",
                None,
                motivo,
            )
            s.flush()  # sem refresh: a ordem já não passa pelo filtro central
            logger.info("OS excluída: os_id=%s usuario_id=%s.", ordem.id, ator.usuario_id)
            return ResultadoLixeira(ordem.id, ordem.numero, ordem.versao)
    except StaleDataError:
        raise ErroConflito() from None


def restaurar_os(ator_id: int, os_id: int, versao: int) -> ResultadoLixeira:
    """Tira a ordem da lixeira; ela volta para todas as consultas, com o mesmo número."""
    ator = carregar_ator(ator_id)
    _exigir_admin(ator, "restaurar OS")
    try:
        with sessao() as s:
            ordem = OrdemServicoRepo(s).obter_excluida(os_id) if ordens._e_int(os_id) else None
            if ordem is None:
                raise ErroNaoEncontrado()
            ordens._conferir_versao(ordem, versao)
            agora = relogio.agora()
            motivo = ordem.motivo_exclusao
            ordem.excluida_em = None
            ordem.excluida_por_id = None
            ordem.motivo_exclusao = None
            ordem.atualizado_em = agora
            ordens.registrar_evento(
                s,
                ordem.id,
                ator.usuario_id,
                ordens.TIPO_RESTAURACAO,
                agora,
                "exclusao",
                motivo,
                None,
            )
            s.flush()
            logger.info("OS restaurada: os_id=%s usuario_id=%s.", ordem.id, ator.usuario_id)
            return ResultadoLixeira(ordem.id, ordem.numero, ordem.versao)
    except StaleDataError:
        raise ErroConflito() from None


def listar_excluidas(ator_id: int, busca: str | None = None, pagina: int = 1) -> PaginaLixeira:
    """Ordens excluídas de todas as filiais, a exclusão mais recente primeiro.

    ``busca``: a mesma condição da lista (ordens.condicao_busca), escopo 'tudo'."""
    ator = carregar_ator(ator_id)
    _exigir_admin(ator, "listar lixeira")
    if not ordens._e_int(pagina) or pagina < 1:
        raise ErroValidacao("pagina", "Página inválida.")
    condicao = ordens.condicao_busca(busca, ordens.ESCOPO_TUDO, ator)
    with sessao() as s:
        linhas = OrdemServicoRepo(s).listar_excluidas(
            condicao, POR_PAGINA + 1, (pagina - 1) * POR_PAGINA
        )
        return PaginaLixeira(
            itens=tuple(_item(o) for o in linhas[:POR_PAGINA]),
            tem_mais=len(linhas) > POR_PAGINA,
        )


def obter_excluida(ator_id: int, os_id: int) -> OsExcluida:
    """Detalhe só de leitura (com o histórico) de uma ordem da lixeira."""
    ator = carregar_ator(ator_id)
    _exigir_admin(ator, "abrir OS da lixeira")
    with sessao() as s:
        ordem = OrdemServicoRepo(s).obter_excluida(os_id) if ordens._e_int(os_id) else None
        if ordem is None:
            raise ErroNaoEncontrado()
        eventos = tuple(
            ordens.EventoDTO(
                data_hora=e.data_hora,
                nome_usuario=e.usuario.nome,
                tipo=e.tipo,
                campo=e.campo,
                valor_antigo=e.valor_antigo,
                valor_novo=e.valor_novo,
                observacao=e.observacao,
            )
            for e in OsEventoRepo(s).listar_por_os(ordem.id)
        )
        detalhe = replace(ordens._detalhe(ordem, ator), acoes=NENHUMA_ACAO)
        return OsExcluida(
            os=detalhe,
            eventos=eventos,
            excluida_em=ordem.excluida_em,
            excluida_por_nome=ordem.excluida_por.nome if ordem.excluida_por else "-",
            motivo=ordem.motivo_exclusao,
        )
