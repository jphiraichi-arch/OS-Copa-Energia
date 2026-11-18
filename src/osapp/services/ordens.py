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

CAMPOS_PREVISTO = ("titulo", "descricao", "tempo_previsto_minutos")
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
class OsResumo:
    id: int
    numero: str
    titulo: str
    status: str
    filial_codigo: str
    total_previsto_centavos: int  # calculado dos itens previstos
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
    pode_editar_itens_previstos: bool
    pode_editar_itens_realizados: bool


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
    tempo_previsto_minutos: int
    equipamento_id: int | None
    equipamento_outro: str | None
    equipamento: str | None  # nome do equipamento ou o texto de 'Outro'
    numero_sap: str | None
    executor_id: int | None
    executor_nome: str | None
    iniciado_em: datetime | None
    inicio_realizado: datetime | None
    fim_realizado: datetime | None
    descricao_realizado: str | None
    concluido_por_id: int | None
    concluido_por_nome: str | None
    concluido_em: datetime | None
    # Os dois abaixo são None até a OS ser concluída.
    tempo_realizado_minutos: int | None
    diferenca_tempo_minutos: int | None  # realizado - previsto
    itens: tuple[custos.ItemDTO, ...]  # previstos e realizados, cada um com o total da linha
    resumo_custos: custos.ResumoCustos  # por categoria e geral; sempre calculado
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


def _pode_editar_itens(ator: Ator, ordem: OrdemServico, fase: str) -> bool:
    """PREVISTO: quem pode editar a OS. REALIZADO: só administrador, depois da conclusão
    (antes disso os itens realizados chegam apenas junto com a conclusão)."""
    if fase == custos.FASE_PREVISTO:
        return _pode_editar(ator, ordem)
    return _pode_editar_realizado(ator, ordem)


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
        pode_editar_itens_previstos=_pode_editar_itens(ator, ordem, custos.FASE_PREVISTO),
        pode_editar_itens_realizados=_pode_editar_itens(ator, ordem, custos.FASE_REALIZADO),
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
        iniciado_em=ordem.iniciado_em,
        inicio_realizado=ordem.inicio_realizado,
        fim_realizado=ordem.fim_realizado,
        descricao_realizado=ordem.descricao_realizado,
        concluido_por_id=ordem.concluido_por_id,
        concluido_por_nome=ordem.concluido_por.nome if ordem.concluido_por else None,
        concluido_em=ordem.concluido_em,
        tempo_realizado_minutos=tempo_realizado,
        diferenca_tempo_minutos=dif_tempo,
        itens=itens,
        resumo_custos=custos.calcular_resumo(itens),
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


def formatar_numero(codigo_filial: str, ano: int, sequencia: int) -> str:
    """Número da OS: '{código da filial}-{ano}-{sequência de 6 dígitos}', ex. 1007-2026-000001."""
    return f"{codigo_filial}-{ano}-{sequencia:06d}"


def _ano_local(instante: datetime) -> int:
    """Ano do número da OS, no fuso da aplicação (OS_TZ)."""
    return instante.astimezone(ZoneInfo(carregar_config().tz)).year


def _validar_equipamento(
    s: Session, filial_id: int, equipamento_id: object, equipamento_outro: object
) -> tuple[int | None, str | None]:
    """Exatamente um: equipamento ativo da filial da OS, ou 'Outro' com texto de 3 a 120."""
    tem_id = equipamento_id is not None
    tem_outro = equipamento_outro is not None and (
        not isinstance(equipamento_outro, str) or equipamento_outro.strip() != ""
    )
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


# --- Funções públicas -----------------------------------------------------------------


def criar_os(
    ator_id: int,
    titulo: str,
    descricao: str,
    itens_previstos: list[custos.ItemEntrada],
    tempo_previsto_minutos: int,
    filial_id: int | None = None,
    *,
    equipamento_id: int | None = None,
    equipamento_outro: str | None = None,
) -> OsDetalhe:
    """Cria a OS e seus itens previstos numa só transação (um evento CRIACAO e um
    ITEM_ADICIONADO por item). Equipamento: ``equipamento_id`` ou ``equipamento_outro``."""
    ator = carregar_ator(ator_id)
    if filial_id is not None and not _e_int(filial_id):
        raise ErroValidacao("filial_id", "Filial inválida.")
    if not ator.is_admin and filial_id is not None and filial_id != ator.filial_id:
        raise _negar(ator, "criar OS em outra filial")
    filial_destino = ator.filial_id if filial_id is None else filial_id

    titulo = _validar_titulo(titulo)
    descricao = _validar_texto_longo("descricao", descricao)
    tempo = _validar_tempo("tempo_previsto_minutos", tempo_previsto_minutos)

    try:
        with sessao() as s:
            filial = FilialRepo(s).obter(filial_destino)
            if filial is None:
                raise ErroValidacao("filial_id", "Filial não encontrada.")
            eq_id, eq_outro = _validar_equipamento(s, filial.id, equipamento_id, equipamento_outro)
            itens = custos.validar_itens_de_entrada(s, itens_previstos, "itens_previstos")
            agora = relogio.agora()
            ano = _ano_local(agora)
            sequencia = OsSequenciaRepo(s).reservar_proximo(filial.id, ano)
            ordem = OrdemServicoRepo(s).adicionar(
                OrdemServico(
                    numero=formatar_numero(filial.codigo, ano, sequencia),
                    filial_id=filial.id,
                    criado_por_id=ator.usuario_id,
                    titulo=titulo,
                    descricao=descricao,
                    status=_status.STATUS_INICIAL,
                    tempo_previsto_minutos=tempo,
                    equipamento_id=eq_id,
                    equipamento_outro=eq_outro,
                    criado_em=agora,
                    atualizado_em=agora,
                )
            )
            registrar_evento(s, ordem.id, ator.usuario_id, TIPO_CRIACAO, agora)
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
                total_previsto_centavos=sum(
                    custos.total_da_linha(i.quantidade, i.valor_unitario_centavos)
                    for i in o.itens
                    if i.fase == custos.FASE_PREVISTO
                ),
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
            permitidos = set(CAMPOS_PREVISTO) | set(CAMPOS_EQUIPAMENTO)
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
                eq_id, eq_outro = _validar_equipamento(s, filial_final, eq_id, eq_outro)
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
    itens_realizados: list[custos.ItemEntrada],
    inicio_realizado: datetime,
    fim_realizado: datetime,
    descricao_realizado: str,
) -> OsDetalhe:
    """Conclui a OS com os itens realizados (pelo menos 1), numa só transação."""
    ator = carregar_ator(ator_id)
    try:
        with sessao() as s:
            ordem = _carregar_visivel(s, ator, os_id)
            if not _pode_transicionar(ator, ordem, _status.CONCLUIDA):
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
            _gravar_itens(s, ordem, ator, custos.FASE_REALIZADO, itens, agora)
            s.flush()
            s.refresh(ordem)
            logger.info("OS concluída: os_id=%s usuario_id=%s.", ordem.id, ator.usuario_id)
            return _detalhe(ordem, ator)
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
                if len(da_fase) <= 1:
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
