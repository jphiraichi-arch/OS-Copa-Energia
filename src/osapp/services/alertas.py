"""Alertas de erro grave (prompt 33).

Um handler de logging para ERROR e CRITICAL. Para cada registro:

- Impressão digital = tipo da exceção + arquivo + linha (do quadro mais interno dentro de
  ``osapp``, ou do mais interno de todos). Sem exceção: o nível + arquivo + linha do log.
- No máximo um alerta por impressão por hora; no máximo 20 e-mails de alerta por dia
  (dia de America/Sao_Paulo) no total. Os contadores ficam no banco (``alertas_erro``,
  ``alertas_dia``), com trava de linha, para valerem entre processos.
- O e-mail vai para a fila do prompt 32, um por administrador ativo com endereço
  confirmado. Com OS_ALERTAS_EMAIL=0, só o log.
- Conteúdo: hora (America/Sao_Paulo), impressão, tela/rota, ocorrências desde o último
  alerta. Nunca a mensagem do log, valores de variáveis, formulários, senhas, tokens,
  endereços de e-mail ou texto de OS.

Segurança contra laço e contra quebrar o pedido:
- ``emit`` só coloca um registro pequeno numa fila em memória (sem banco, sem rede) e
  nunca levanta exceção;
- o banco é usado por uma thread própria; registros dessa thread e deste módulo são
  ignorados pelo handler; falhas lá viram WARNING (que o handler não pega).
"""

from __future__ import annotations

import contextvars
import logging
import os
import queue
import threading
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError

from osapp import config
from osapp.db import sessao
from osapp.models import AlertaDia, AlertaErro, EmailFila
from osapp.models.notificacao import FILA_PENDENTE, TIPO_ALERTA
from osapp.repositories import AlertaRepo, EmailFilaRepo
from osapp.services import email_mensagem, relogio

logger = logging.getLogger(__name__)

INTERVALO = timedelta(hours=1)
MAX_EMAILS_DIA = 20
FUSO = "America/Sao_Paulo"
FILA_MAX = 1000
NOME_THREAD = "osapp-alertas"

# Tela/rota atual (nome da rota, ex.: 'os_detalhe'); definida pela interface antes de
# chamar um serviço. asyncio.to_thread copia o contexto, então vale dentro do serviço.
ROTA: contextvars.ContextVar[str | None] = contextvars.ContextVar("osapp_rota", default=None)


@dataclass(frozen=True)
class Ocorrencia:
    impressao: str
    nivel: str
    rota: str | None
    instante: datetime


# --- Impressão digital ----------------------------------------------------------------------


def _arquivo_curto(caminho: str) -> str:
    """Só as duas últimas partes do caminho ('services/ordens.py'): sem pastas do
    servidor."""
    partes = caminho.replace("\\", "/").split("/")
    return "/".join(partes[-2:])


def impressao_de(record: logging.LogRecord) -> str:
    if record.exc_info and record.exc_info[1] is not None:
        tipo, exc, tb = record.exc_info
        quadros = traceback.extract_tb(tb) if tb is not None else []
        do_app = [q for q in quadros if "/osapp/" in q.filename.replace("\\", "/")]
        quadro = (do_app or quadros or [None])[-1]
        nome = tipo.__name__ if tipo is not None else type(exc).__name__
        if quadro is not None:
            return f"{nome}:{_arquivo_curto(quadro.filename)}:{quadro.lineno}"[:200]
        return f"{nome}:{_arquivo_curto(record.pathname)}:{record.lineno}"[:200]
    return f"{record.levelname}:{_arquivo_curto(record.pathname)}:{record.lineno}"[:200]


# --- Regra (banco) ---------------------------------------------------------------------------


def _assunto(oc: Ocorrencia) -> str:
    tipo = oc.impressao.split(":", 1)[0]
    return email_mensagem.limpar_linha(f"[Sistema de OS] Erro grave: {tipo}")[:150]


def _corpo(oc: Ocorrencia, ocorrencias: int) -> str:
    quando = oc.instante.astimezone(ZoneInfo(FUSO)).strftime("%d/%m/%Y %H:%M")
    return (
        "Erro grave no Sistema de OS.\n"
        "\n"
        f"Quando: {quando} (horário de Brasília)\n"
        f"Nível: {oc.nivel}\n"
        f"Erro: {email_mensagem.limpar_linha(oc.impressao)}\n"
        f"Tela/rota: {email_mensagem.limpar_linha(oc.rota or 'desconhecida')}\n"
        f"Ocorrências desde o último alerta: {ocorrencias}\n"
        "\n"
        "Os detalhes estão no log do servidor, perto deste horário.\n"
        "Você recebe este aviso por ser administrador com e-mail confirmado.\n"
    )


def _obter_ou_criar(repo: AlertaRepo, obter, novo):
    registro = obter()
    if registro is None:
        repo.adicionar(novo)
        registro = novo
    return registro


def registrar(oc: Ocorrencia) -> int:
    """Conta a ocorrência e, se os limites deixarem, põe os e-mails na fila.
    Devolve quantos e-mails foram para a fila. Síncrona (thread dos alertas, testes)."""
    for tentativa in range(2):  # outra instância pode criar a mesma linha ao mesmo tempo
        try:
            return _registrar(oc)
        except IntegrityError:
            if tentativa == 1:
                raise
    return 0


def _registrar(oc: Ocorrencia) -> int:
    agora = oc.instante
    with sessao() as s:
        repo = AlertaRepo(s)
        erro = _obter_ou_criar(
            repo,
            lambda: repo.erro_para_alterar(oc.impressao),
            AlertaErro(impressao=oc.impressao, ultima_ocorrencia_em=agora),
        )
        erro.ocorrencias_pendentes += 1
        erro.ultima_ocorrencia_em = agora
        if erro.ultimo_alerta_em is not None and agora - erro.ultimo_alerta_em < INTERVALO:
            return 0
        logger.warning(
            "Alerta de erro grave: impressao=%s rota=%s ocorrencias=%s.",
            oc.impressao,
            oc.rota or "desconhecida",
            erro.ocorrencias_pendentes,
        )
        if not config.alertas_por_email():
            erro.ultimo_alerta_em = agora
            erro.ocorrencias_pendentes = 0
            return 0
        destinos = repo.admins_com_email_confirmado()
        if not destinos:
            erro.ultimo_alerta_em = agora
            erro.ocorrencias_pendentes = 0
            return 0
        dia_local = agora.astimezone(ZoneInfo(FUSO)).date()
        dia = _obter_ou_criar(
            repo, lambda: repo.dia_para_alterar(dia_local), AlertaDia(dia=dia_local, emails=0)
        )
        if dia.emails + len(destinos) > MAX_EMAILS_DIA:
            logger.warning("Alerta não enviado: teto de %s e-mails por dia.", MAX_EMAILS_DIA)
            return 0  # fica pendente: as ocorrências somam para o próximo alerta
        fila = EmailFilaRepo(s)
        corpo = _corpo(oc, erro.ocorrencias_pendentes)
        for usuario_id, endereco in destinos:
            fila.adicionar(
                EmailFila(
                    tipo=TIPO_ALERTA,
                    destinatario=endereco,
                    assunto=_assunto(oc),
                    corpo=corpo,
                    status=FILA_PENDENTE,
                    proxima_tentativa_em=agora,
                    criado_em=agora,
                    usuario_id=usuario_id,
                )
            )
        dia.emails += len(destinos)
        erro.ultimo_alerta_em = agora
        erro.ocorrencias_pendentes = 0
        return len(destinos)


# --- Handler -------------------------------------------------------------------------------


class ManipuladorAlertas(logging.Handler):
    """Só enfileira em memória; uma thread própria grava no banco."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self._fila: queue.Queue[Ocorrencia] = queue.Queue(maxsize=FILA_MAX)
        self._thread: threading.Thread | None = None
        self._pid: int | None = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.name.startswith(__name__) or self._na_thread_dos_alertas():
                return  # nunca um alerta sobre o próprio alerta
            oc = Ocorrencia(impressao_de(record), record.levelname, ROTA.get(), relogio.agora())
            self._garantir_thread()
            self._fila.put_nowait(oc)
        except Exception:  # noqa: BLE001 - o handler nunca quebra quem registrou o erro
            pass

    @staticmethod
    def _na_thread_dos_alertas() -> bool:
        """Qualquer thread de alertas (de qualquer handler): nada que aconteça lá vira
        alerta."""
        return threading.current_thread().name.startswith(NOME_THREAD)

    def _garantir_thread(self) -> None:
        if self._thread is None or not self._thread.is_alive() or self._pid != os.getpid():
            self._pid = os.getpid()
            self._thread = threading.Thread(target=self._drenar, name=NOME_THREAD, daemon=True)
            self._thread.start()

    def _drenar(self) -> None:
        while True:
            oc = self._fila.get()
            try:
                registrar(oc)
            except Exception as exc:  # noqa: BLE001 - WARNING: o handler não pega
                logger.warning("Alerta não registrado: %s.", type(exc).__name__)


_instalado: ManipuladorAlertas | None = None


def instalar() -> ManipuladorAlertas:
    """Liga o handler no logger raiz (uma vez por processo). Chamado na partida do app."""
    global _instalado
    if _instalado is None:
        _instalado = ManipuladorAlertas()
        logging.getLogger().addHandler(_instalado)
    return _instalado
