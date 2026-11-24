"""Envio da fila de e-mails (caixa de saída transacional, prompt 32).

Um trabalhador por processo, iniciado uma vez na subida do app ASGI (osapp/main.py,
``on_startup`` do FastAPI do Flet) — nunca no ``main()`` do Flet, que roda uma vez por
sessão de navegador. A cada 15 segundos:

1. linhas 'enviando' com a concessão (``bloqueado_ate``) vencida voltam a 'pendente'
   (o processo morreu no meio do envio);
2. reserva um lote pequeno de linhas 'pendente' e vencidas, de forma atômica:
   PostgreSQL ``SELECT ... FOR UPDATE SKIP LOCKED`` e status 'enviando' com concessão de
   5 minutos. SQLite (desenvolvimento, um processo): reserva simples, sem SKIP LOCKED —
   a escrita do SQLite já é exclusiva por banco;
3. aviso de OS que foi para a lixeira vira 'cancelado';
4. envia pelo SMTP (bloqueante, numa thread: o app continua respondendo);
5. falha: tentativas + 1 e nova tentativa em 1, 2, 4, 8... minutos (teto de 60) com um
   pouco de variação; ao chegar a OS_EMAIL_MAX_TENTATIVAS (padrão 6) vira 'falhou'.

Entrega "pelo menos uma vez": uma queda logo depois de um envio bem-sucedido reenvia a
mensagem. O Message-ID é estável (vem do id da linha) para o cliente de e-mail reconhecer
a cópia.

Configuração SMTP só por variáveis de ambiente. Sem configuração, as linhas ficam
pendentes e um aviso vai para o log uma vez por hora; o app nunca cai por isso.
Logs: id da linha e endereço mascarado (j***@dominio); nunca o endereço inteiro, o corpo
nem a senha.
"""

from __future__ import annotations

import asyncio
import logging
import random
import smtplib
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage

from osapp import config
from osapp.db import sessao
from osapp.models.notificacao import (
    FILA_CANCELADO,
    FILA_ENVIADO,
    FILA_FALHOU,
    FILA_PENDENTE,
    FILA_STATUS,
    TIPO_CODIGO,
    TIPO_NOVA_SOLICITACAO,
)
from osapp.repositories import EmailFilaRepo
from osapp.services import email_mensagem, relogio
from osapp.services.auth import carregar_ator
from osapp.services.erros import ErroNaoEncontrado, ErroValidacao
from osapp.services.permissoes import exigir_admin

logger = logging.getLogger(__name__)

INTERVALO_SEGUNDOS = 15
LOTE = 10
CONCESSAO = timedelta(minutes=5)
TIMEOUT_SMTP = 10  # segundos por conexão
ESPERA_MAX_MINUTOS = 60
MAX_TENTATIVAS_PADRAO = 6
AVISO_SEM_CONFIG = timedelta(hours=1)
ERRO_MAX = 200
RETENCAO_ENVIADOS = timedelta(days=30)  # 'enviado' e 'cancelado'
RETENCAO_FALHOS = timedelta(days=90)  # 'falhou'
ULTIMOS_ERROS = 20

VAR_HOST = "OS_SMTP_HOST"
VAR_PORTA = "OS_SMTP_PORTA"
VAR_USUARIO = "OS_SMTP_USUARIO"
VAR_SENHA = "OS_SMTP_SENHA"
VAR_REMETENTE = "OS_SMTP_REMETENTE"
VAR_TLS = "OS_SMTP_TLS"
VAR_MAX_TENTATIVAS = "OS_EMAIL_MAX_TENTATIVAS"

TLS_STARTTLS = "starttls"
TLS_SSL = "ssl"
# Só para um coletor local de desenvolvimento (Mailpit, aiosmtpd): sem TLS e só em
# localhost. Nunca aceito com outro host.
TLS_NENHUM = "nenhum"
HOSTS_LOCAIS = ("localhost", "127.0.0.1", "::1")

MSG_SO_FALHOU = "Só um e-mail que falhou pode ser reenviado."


# --- Configuração -----------------------------------------------------------------------


@dataclass(frozen=True)
class ConfigSmtp:
    host: str
    porta: int
    usuario: str | None
    senha: str | None
    remetente: str
    tls: str

    def __repr__(self) -> str:  # a senha nunca aparece em log nem em traceback
        return (
            f"ConfigSmtp(host={self.host!r}, porta={self.porta}, tls={self.tls!r}, "
            f"remetente={email_mensagem.mascarar(self.remetente)!r})"
        )


def ler_config_smtp() -> ConfigSmtp | None:
    """A configuração do SMTP, ou None se faltar ou estiver inválida (o motivo, sem
    valores, vai para o log)."""
    bruto = config.smtp()
    host, porta_txt, tls = bruto.host, bruto.porta, bruto.tls
    remetente = email_mensagem.normalizar_email(bruto.remetente)
    usuario, senha = bruto.usuario, bruto.senha
    if not host or not porta_txt or remetente is None or not tls:
        return None
    problema = None
    if not porta_txt.isdigit() or not 0 < int(porta_txt) < 65536:
        problema = f"{VAR_PORTA} inválida"
    elif tls not in (TLS_STARTTLS, TLS_SSL, TLS_NENHUM):
        problema = f"{VAR_TLS} deve ser 'starttls' ou 'ssl'"
    elif tls == TLS_NENHUM and host not in HOSTS_LOCAIS:
        problema = f"{VAR_TLS}='nenhum' só é aceito com host local"
    elif (usuario is None) != (senha is None):
        problema = f"{VAR_USUARIO} e {VAR_SENHA} vão juntos"
    if problema:
        logger.error("Configuração de e-mail inválida: %s. Nada será enviado.", problema)
        return None
    return ConfigSmtp(host, int(porta_txt), usuario, senha, remetente, tls)


def max_tentativas() -> int:
    return config.email_max_tentativas(MAX_TENTATIVAS_PADRAO)


def espera(tentativas: int, sorteio: Callable[[], float] = random.random) -> timedelta:
    """Espera antes da próxima tentativa: 1, 2, 4, 8... minutos (teto de 60), mais até
    10% de variação para os reenvios não saírem todos juntos."""
    minutos = min(2 ** max(tentativas - 1, 0), ESPERA_MAX_MINUTOS)
    return timedelta(minutes=minutos) * (1 + 0.1 * sorteio())


# --- SMTP ---------------------------------------------------------------------------------


def enviar_smtp(config: ConfigSmtp, mensagem: EmailMessage) -> None:
    """Envio bloqueante, com tempo-limite de 10 segundos por conexão."""
    contexto = ssl.create_default_context()
    if config.tls == TLS_SSL:
        conexao: smtplib.SMTP = smtplib.SMTP_SSL(
            config.host, config.porta, timeout=TIMEOUT_SMTP, context=contexto
        )
    else:
        conexao = smtplib.SMTP(config.host, config.porta, timeout=TIMEOUT_SMTP)
    with conexao:
        if config.tls == TLS_STARTTLS:
            conexao.starttls(context=contexto)
        if config.usuario is not None and config.senha is not None:
            conexao.login(config.usuario, config.senha)
        conexao.send_message(mensagem)


def descrever_erro(exc: BaseException) -> str:
    """Texto curto do erro, sem dados: o nome da exceção e o código SMTP, se houver.
    A mensagem do servidor não é gravada (pode repetir o endereço ou o usuário)."""
    codigo = getattr(exc, "smtp_code", None)
    texto = type(exc).__name__ + (f" {codigo}" if isinstance(codigo, int) else "")
    return texto[:ERRO_MAX]


# --- Lote ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Reservada:
    id: int
    tipo: str
    destinatario: str
    assunto: str
    corpo: str
    tentativas: int


@dataclass(frozen=True)
class ResultadoLote:
    enviados: int = 0
    falhas: int = 0
    cancelados: int = 0
    sem_config: bool = False


def reservar(agora: datetime, limite: int = LOTE) -> tuple[list[_Reservada], int]:
    """Uma transação: devolve as travadas, reserva o lote e cancela avisos de OS
    excluída. Devolve (reservadas, canceladas)."""
    reservadas: list[_Reservada] = []
    canceladas = 0
    with sessao() as s:
        repo = EmailFilaRepo(s)
        repo.devolver_travadas(agora)
        for linha in repo.reservar(agora, limite, agora + CONCESSAO):
            if (
                linha.tipo == TIPO_NOVA_SOLICITACAO
                and linha.os_id is not None
                and repo.ordem_excluida(linha.os_id)
            ):
                linha.status = FILA_CANCELADO
                linha.bloqueado_ate = None
                linha.corpo = ""
                canceladas += 1
                logger.info("E-mail cancelado (OS excluída): linha=%s.", linha.id)
                continue
            reservadas.append(
                _Reservada(
                    linha.id,
                    linha.tipo,
                    linha.destinatario,
                    linha.assunto,
                    linha.corpo,
                    linha.tentativas,
                )
            )
    return reservadas, canceladas


def _concluir(linha_id: int, erro: BaseException | None, agora: datetime) -> str:
    """Grava o resultado do envio. Devolve o novo status."""
    with sessao() as s:
        linha = EmailFilaRepo(s).obter(linha_id)
        if linha is None:
            return FILA_CANCELADO
        linha.bloqueado_ate = None
        if erro is None:
            linha.status = FILA_ENVIADO
            linha.enviado_em = agora
            linha.ultimo_erro = None
            if linha.tipo == TIPO_CODIGO:
                linha.corpo = ""  # o código só existe enquanto não foi enviado
            return linha.status
        linha.tentativas += 1
        linha.ultimo_erro = descrever_erro(erro)
        if linha.tentativas >= max_tentativas():
            linha.status = FILA_FALHOU
            if linha.tipo == TIPO_CODIGO:
                linha.corpo = ""
        else:
            linha.status = FILA_PENDENTE
            linha.proxima_tentativa_em = agora + espera(linha.tentativas)
        return linha.status


def processar_lote(
    enviar: Callable[[ConfigSmtp, EmailMessage], None] = enviar_smtp,
    config: ConfigSmtp | None = None,
    limite: int = LOTE,
) -> ResultadoLote:
    """Uma rodada do trabalhador. Bloqueante: chamada numa thread."""
    config = config or ler_config_smtp()
    if config is None:
        return ResultadoLote(sem_config=True)
    agora = relogio.agora()
    reservadas, canceladas = reservar(agora, limite)
    enviados = falhas = 0
    for r in reservadas:
        mensagem = email_mensagem.montar_mensagem(
            r.id, config.remetente, r.destinatario, r.assunto, r.corpo, agora
        )
        try:
            enviar(config, mensagem)
            erro: BaseException | None = None
        except Exception as exc:  # noqa: BLE001 - qualquer falha de rede/SMTP vira nova tentativa
            erro = exc
        status = _concluir(r.id, erro, relogio.agora())
        destino = email_mensagem.mascarar(r.destinatario)
        if erro is None:
            enviados += 1
            logger.info("E-mail enviado: linha=%s destino=%s.", r.id, destino)
        else:
            falhas += 1
            logger.warning(
                "Falha ao enviar e-mail: linha=%s destino=%s erro=%s status=%s.",
                r.id,
                destino,
                descrever_erro(erro),
                status,
            )
    return ResultadoLote(enviados, falhas, canceladas)


# --- Trabalhador --------------------------------------------------------------------------


class Trabalhador:
    """Laço assíncrono do processo. ``iniciar`` e ``parar`` vão no on_startup e no
    on_shutdown do app ASGI."""

    def __init__(self, intervalo: float = INTERVALO_SEGUNDOS) -> None:
        self.intervalo = intervalo
        self._tarefa: asyncio.Task | None = None
        self._ultimo_aviso: datetime | None = None

    def _avisar_sem_config(self) -> None:
        agora = relogio.agora()
        if self._ultimo_aviso is None or agora - self._ultimo_aviso >= AVISO_SEM_CONFIG:
            self._ultimo_aviso = agora
            logger.warning("E-mail não configurado (OS_SMTP_*): os avisos ficam pendentes na fila.")

    async def rodada(self) -> ResultadoLote:
        resultado = await asyncio.to_thread(processar_lote)
        if resultado.sem_config:
            self._avisar_sem_config()
        return resultado

    async def _laco(self) -> None:
        while True:
            try:
                await self.rodada()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - o trabalhador nunca derruba o app
                logger.exception("Erro na rodada da fila de e-mails.")
            await asyncio.sleep(self.intervalo)

    def iniciar(self) -> None:
        if self._tarefa is None or self._tarefa.done():
            self._tarefa = asyncio.get_running_loop().create_task(self._laco())
            logger.info("Fila de e-mails: trabalhador iniciado (a cada %ss).", self.intervalo)

    async def parar(self) -> None:
        if self._tarefa is not None:
            self._tarefa.cancel()
            try:
                await self._tarefa
            except asyncio.CancelledError:
                pass
            self._tarefa = None


# --- Administração --------------------------------------------------------------------


@dataclass(frozen=True)
class LinhaComErro:
    id: int
    tipo: str
    status: str
    tentativas: int
    destino: str  # mascarado
    erro: str
    criado_em: datetime
    pode_reenviar: bool


@dataclass(frozen=True)
class ResumoFila:
    contagens: dict[str, int]
    erros: tuple[LinhaComErro, ...]
    configurado: bool


def resumo_fila(ator_id: int) -> ResumoFila:
    """Só administrador. Contagens por status e os últimos erros, sem corpo de mensagem
    e com o endereço mascarado."""
    exigir_admin(carregar_ator(ator_id))
    with sessao() as s:
        repo = EmailFilaRepo(s)
        contagem = repo.contagem_por_status()
        erros = tuple(
            LinhaComErro(
                id=linha.id,
                tipo=linha.tipo,
                status=linha.status,
                tentativas=linha.tentativas,
                destino=email_mensagem.mascarar(linha.destinatario),
                erro=linha.ultimo_erro or "",
                criado_em=linha.criado_em,
                pode_reenviar=linha.status == FILA_FALHOU and linha.tipo != TIPO_CODIGO,
            )
            for linha in repo.ultimas_com_erro(ULTIMOS_ERROS)
        )
    return ResumoFila(
        {st: contagem.get(st, 0) for st in FILA_STATUS},
        erros,
        ler_config_smtp() is not None,
    )


def reenviar(ator_id: int, linha_id: object) -> None:
    """Só administrador; só linha 'falhou'. Volta a 'pendente' com as tentativas
    zeradas. Um código de confirmação que falhou não é reenviado (o corpo já foi
    apagado): o usuário pede outro."""
    ator = carregar_ator(ator_id)
    exigir_admin(ator)
    with sessao() as s:
        linha = EmailFilaRepo(s).obter(linha_id) if isinstance(linha_id, int) else None
        if linha is None:
            raise ErroNaoEncontrado()
        if linha.status != FILA_FALHOU or linha.tipo == TIPO_CODIGO:
            raise ErroValidacao("linha", MSG_SO_FALHOU)
        linha.status = FILA_PENDENTE
        linha.tentativas = 0
        linha.proxima_tentativa_em = relogio.agora()
        logger.info(
            "E-mail reenviado pelo administrador: linha=%s autor_id=%s.", linha.id, ator.usuario_id
        )


def limpar_fila(agora: datetime | None = None) -> tuple[int, int]:
    """Retenção (comando de linha): apaga 'enviado' e 'cancelado' com mais de 30 dias e
    'falhou' com mais de 90. Devolve (enviados/cancelados apagados, falhos apagados)."""
    agora = agora or relogio.agora()
    with sessao() as s:
        repo = EmailFilaRepo(s)
        a = repo.apagar((FILA_ENVIADO, FILA_CANCELADO), agora - RETENCAO_ENVIADOS)
        b = repo.apagar((FILA_FALHOU,), agora - RETENCAO_FALHOS)
    return a, b
