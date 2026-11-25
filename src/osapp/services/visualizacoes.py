"""'Visualizada' (prompt 42): a manutenção abriu o detalhe da solicitação.

Regras:
- Conta só quem tem papel manutenção (administrador só com
  ``config.CONTAR_VISUALIZACAO_ADMIN``), numa OS de origem 'solicitacao', visível para ele
  (filial permitida, fora da lixeira), quando NÃO é o solicitante, e só ao abrir o
  detalhe (``registrar_visualizacao``, chamada só pela tela Detalhe) ou ao iniciar a
  execução (na mesma transação, para o início nunca vir antes da primeira visualização).
  Lista, busca, contadores e relatório nunca registram.
- Gravação: INSERT ... ON CONFLICT (os_id, usuario_id) DO NOTHING RETURNING id (dialetos
  do PostgreSQL e do SQLite do SQLAlchemy) e, se a linha já existia, UPDATE de
  ultima_visualizacao_em: seguro com acessos simultâneos, nunca 'ler e depois inserir'.
  (O DO UPDATE ... RETURNING do prompt não diz, sozinho, se a linha foi criada.)
- Só a primeira visualização de cada pessoa vai para o histórico (VISUALIZACAO,
  'Visualizada por <nome>'); as seguintes só atualizam ``ultima_visualizacao_em``.
  ``primeira_visualizacao_em`` nunca muda.
- Uma falha ao registrar nunca impede abrir o detalhe: vai para o log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as insert_pg
from sqlalchemy.dialects.sqlite import insert as insert_sqlite
from sqlalchemy.orm import Session

from osapp import config
from osapp.db import sessao
from osapp.models import OsVisualizacao, Usuario
from osapp.services import relogio
from osapp.services.auth import Ator, carregar_ator
from osapp.services.erros import ErroAutenticacao, ErroDominio

logger = logging.getLogger(__name__)

TIPO_VISUALIZACAO = "VISUALIZACAO"
ORIGEM_SOLICITACAO = "solicitacao"


@dataclass(frozen=True)
class Visualizador:
    nome: str
    primeira_em: datetime
    ultima_em: datetime


def conta(ator: Ator, ordem) -> bool:
    """A regra de quem conta (a visibilidade da OS já foi conferida por quem chama)."""
    if ator.e_manutencao:
        papel_ok = True
    elif ator.e_admin:
        papel_ok = config.CONTAR_VISUALIZACAO_ADMIN
    else:
        papel_ok = False
    return (
        papel_ok
        and ordem.origem == ORIGEM_SOLICITACAO
        and ordem.criado_por_id != ator.usuario_id
        and getattr(ordem, "excluida_em", None) is None
    )


def _upsert(s: Session, os_id: int, usuario_id: int, agora: datetime) -> bool:
    """Grava ou atualiza; True se a linha foi criada agora (primeira visualização).

    INSERT ... ON CONFLICT (os_id, usuario_id) DO NOTHING RETURNING id: uma linha de
    volta quer dizer que ESTE comando a criou (só um de vários acessos simultâneos
    recebe). Sem linha de volta, ela já existia e só ``ultima_visualizacao_em`` é
    atualizada. Nunca 'ler e depois inserir'.
    """
    tabela = OsVisualizacao.__table__
    construtor = insert_pg if s.get_bind().dialect.name == "postgresql" else insert_sqlite
    criada = s.execute(
        construtor(tabela)
        .values(
            os_id=os_id,
            usuario_id=usuario_id,
            primeira_visualizacao_em=agora,
            ultima_visualizacao_em=agora,
        )
        .on_conflict_do_nothing(index_elements=[tabela.c.os_id, tabela.c.usuario_id])
        .returning(tabela.c.id)
    ).first()
    if criada is not None:
        return True
    s.execute(
        update(tabela)
        .where(tabela.c.os_id == os_id, tabela.c.usuario_id == usuario_id)
        .values(ultima_visualizacao_em=func.greatest(tabela.c.ultima_visualizacao_em, agora))
        if s.get_bind().dialect.name == "postgresql"
        else update(tabela)
        .where(tabela.c.os_id == os_id, tabela.c.usuario_id == usuario_id)
        .values(ultima_visualizacao_em=agora)
    )
    return False


def registrar(s: Session, ator: Ator, ordem, agora: datetime) -> bool:
    """Dentro de uma transação já aberta (Detalhe ou iniciar_execucao). True se foi a
    primeira visualização desta pessoa (e o evento foi gravado)."""
    if not conta(ator, ordem):
        return False
    from osapp.services.ordens import registrar_evento  # evita import circular

    criada = _upsert(s, ordem.id, ator.usuario_id, agora)
    if criada:
        registrar_evento(
            s, ordem.id, ator.usuario_id, TIPO_VISUALIZACAO, agora, None, None, ator.nome
        )
        logger.info("OS visualizada: os_id=%s usuario_id=%s.", ordem.id, ator.usuario_id)
    return criada


def registrar_visualizacao(ator_id: int, os_id: object) -> bool:
    """Chamada só pela tela Detalhe, antes de mostrar a OS. Nunca impede abrir o
    detalhe: qualquer falha vai para o log e devolve False (a sessão inválida, não)."""
    try:
        ator = carregar_ator(ator_id)
        from osapp.services.ordens import _carregar_visivel

        with sessao() as s:
            ordem = _carregar_visivel(s, ator, os_id)
            return registrar(s, ator, ordem, relogio.agora())
    except ErroAutenticacao:
        raise
    except ErroDominio:
        return False  # OS não encontrada ou não visível: o detalhe mostra o mesmo erro
    except Exception:  # noqa: BLE001 - registrar nunca quebra abrir o detalhe
        logger.exception("Falha ao registrar a visualização: os_id=%s.", os_id)
        return False


# --- Leitura (sessão aberta) ---------------------------------------------------------------


def visualizadores(s: Session, os_id: int) -> tuple[Visualizador, ...]:
    linhas = s.execute(
        select(
            Usuario.nome,
            OsVisualizacao.primeira_visualizacao_em,
            OsVisualizacao.ultima_visualizacao_em,
        )
        .join(Usuario, Usuario.id == OsVisualizacao.usuario_id)
        .where(OsVisualizacao.os_id == os_id)
        .order_by(OsVisualizacao.primeira_visualizacao_em, OsVisualizacao.id)
    ).all()
    return tuple(Visualizador(n, p, u) for n, p, u in linhas)


def visualizadas(s: Session, os_ids) -> set[int]:
    ids = list(os_ids)
    if not ids:
        return set()
    return set(
        s.scalars(select(OsVisualizacao.os_id).where(OsVisualizacao.os_id.in_(ids)).distinct())
    )


def primeiras(s: Session, os_ids, antes_de: datetime | None = None) -> dict[int, datetime]:
    """os_id -> primeira visualização (de qualquer pessoa), opcionalmente só antes de
    ``antes_de`` (uma visualização depois do fim do período não conta para ele)."""
    ids = list(os_ids)
    if not ids:
        return {}
    consulta = (
        select(OsVisualizacao.os_id, func.min(OsVisualizacao.primeira_visualizacao_em))
        .where(OsVisualizacao.os_id.in_(ids))
        .group_by(OsVisualizacao.os_id)
    )
    if antes_de is not None:
        consulta = consulta.where(OsVisualizacao.primeira_visualizacao_em < antes_de)
    from osapp.models.tipos import DataHoraUTC

    conv = DataHoraUTC().process_result_value
    return {i: conv(m, None) for i, m in s.execute(consulta).all()}
