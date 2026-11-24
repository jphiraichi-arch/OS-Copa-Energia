"""Acesso a usuario_notificacao e email_fila. Sem regra de negócio nem permissão."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from osapp.models import (
    AlertaDia,
    AlertaErro,
    EmailFila,
    OrdemServico,
    Usuario,
    UsuarioNotificacao,
)
from osapp.models.notificacao import FILA_CANCELADO, FILA_ENVIANDO, FILA_PENDENTE
from osapp.models.ordem_servico import INCLUIR_EXCLUIDAS


class NotificacaoRepo:
    def __init__(self, sessao: Session) -> None:
        self._s = sessao

    def obter(self, usuario_id: int) -> UsuarioNotificacao | None:
        return self._s.get(UsuarioNotificacao, usuario_id)

    def obter_para_alterar(self, usuario_id: int) -> UsuarioNotificacao | None:
        """Com trava de linha no PostgreSQL (dois pedidos de código ao mesmo tempo)."""
        return self._s.scalars(
            select(UsuarioNotificacao)
            .where(UsuarioNotificacao.usuario_id == usuario_id)
            .with_for_update()
        ).one_or_none()

    def adicionar(self, registro: UsuarioNotificacao) -> UsuarioNotificacao:
        self._s.add(registro)
        self._s.flush()
        return registro

    def candidatos(self, papeis: tuple[str, ...]) -> list[tuple[Usuario, UsuarioNotificacao]]:
        """Usuários ativos dos papéis dados, com endereço confirmado e notificações ligadas.

        Filial e urgência mínima são decididas no serviço.
        """
        linhas = self._s.execute(
            select(Usuario, UsuarioNotificacao)
            .join(UsuarioNotificacao, UsuarioNotificacao.usuario_id == Usuario.id)
            .where(
                Usuario.ativo.is_(True),
                Usuario.papel.in_(papeis),
                UsuarioNotificacao.notificacoes_ativas.is_(True),
                UsuarioNotificacao.email.is_not(None),
                UsuarioNotificacao.email_confirmado_em.is_not(None),
            )
            .order_by(Usuario.id)
        )
        return [(u, n) for u, n in linhas]


class EmailFilaRepo:
    def __init__(self, sessao: Session) -> None:
        self._s = sessao

    def adicionar(self, linha: EmailFila) -> EmailFila:
        self._s.add(linha)
        self._s.flush()
        return linha

    def obter(self, linha_id: int) -> EmailFila | None:
        return self._s.get(EmailFila, linha_id)

    def devolver_travadas(self, agora: datetime) -> int:
        """'enviando' com a concessão vencida (o processo morreu no meio) volta a
        'pendente'."""
        resultado = self._s.execute(
            update(EmailFila)
            .where(EmailFila.status == FILA_ENVIANDO, EmailFila.bloqueado_ate < agora)
            .values(status=FILA_PENDENTE, bloqueado_ate=None)
            .execution_options(synchronize_session=False)
        )
        return resultado.rowcount or 0

    def reservar(self, agora: datetime, limite: int, ate: datetime) -> list[EmailFila]:
        """Reserva até ``limite`` linhas pendentes e vencidas: status 'enviando' com
        concessão até ``ate``.

        PostgreSQL: SELECT ... FOR UPDATE SKIP LOCKED, então dois processos nunca pegam a
        mesma linha. SQLite: o SQLAlchemy não gera FOR UPDATE; a escrita do SQLite já é
        exclusiva por banco e o desenvolvimento roda um processo só.
        """
        linhas = list(
            self._s.scalars(
                select(EmailFila)
                .where(EmailFila.status == FILA_PENDENTE, EmailFila.proxima_tentativa_em <= agora)
                .order_by(EmailFila.proxima_tentativa_em, EmailFila.id)
                .limit(limite)
                .with_for_update(skip_locked=True)
            )
        )
        for linha in linhas:
            linha.status = FILA_ENVIANDO
            linha.bloqueado_ate = ate
        self._s.flush()
        return linhas

    def ordem_excluida(self, os_id: int) -> bool:
        """True se a OS foi para a lixeira (ou não existe mais)."""
        excluida = self._s.execute(
            select(OrdemServico.excluida_em)
            .where(OrdemServico.id == os_id)
            .execution_options(**{INCLUIR_EXCLUIDAS: True})
        ).one_or_none()
        return excluida is None or excluida[0] is not None

    def cancelar_pendentes(self, *condicoes) -> int:
        resultado = self._s.execute(
            update(EmailFila)
            .where(EmailFila.status == FILA_PENDENTE, *condicoes)
            .values(status=FILA_CANCELADO, corpo="")
            .execution_options(synchronize_session=False)
        )
        return resultado.rowcount or 0

    def contagem_por_status(self) -> dict[str, int]:
        return dict(
            self._s.execute(select(EmailFila.status, func.count()).group_by(EmailFila.status)).all()
        )

    def ultimas_com_erro(self, limite: int) -> list[EmailFila]:
        return list(
            self._s.scalars(
                select(EmailFila)
                .where(EmailFila.ultimo_erro.is_not(None))
                .order_by(EmailFila.id.desc())
                .limit(limite)
            )
        )

    def apagar(self, status: tuple[str, ...], antes_de: datetime) -> int:
        resultado = self._s.execute(
            delete(EmailFila)
            .where(EmailFila.status.in_(status), EmailFila.criado_em < antes_de)
            .execution_options(synchronize_session=False)
        )
        return resultado.rowcount or 0


class AlertaRepo:
    """Contadores dos alertas de erro grave (prompt 33)."""

    def __init__(self, sessao: Session) -> None:
        self._s = sessao

    def erro_para_alterar(self, impressao: str) -> AlertaErro | None:
        return self._s.scalars(
            select(AlertaErro).where(AlertaErro.impressao == impressao).with_for_update()
        ).one_or_none()

    def dia_para_alterar(self, dia: date) -> AlertaDia | None:
        return self._s.scalars(
            select(AlertaDia).where(AlertaDia.dia == dia).with_for_update()
        ).one_or_none()

    def adicionar(self, registro) -> None:
        self._s.add(registro)
        self._s.flush()

    def admins_com_email_confirmado(self) -> list[tuple[int, str]]:
        """(usuario_id, email) dos administradores ativos com endereço confirmado."""
        return list(
            self._s.execute(
                select(Usuario.id, UsuarioNotificacao.email)
                .join(UsuarioNotificacao, UsuarioNotificacao.usuario_id == Usuario.id)
                .where(
                    Usuario.ativo.is_(True),
                    Usuario.papel == "admin",
                    UsuarioNotificacao.email.is_not(None),
                    UsuarioNotificacao.email_confirmado_em.is_not(None),
                )
                .order_by(Usuario.id)
            ).all()
        )
