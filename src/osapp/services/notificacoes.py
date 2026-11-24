"""Notificações por e-mail: endereço confirmado e consentimento (prompt 32).

Dado pessoal (LGPD): o endereço só é gravado por ação do próprio usuário, só serve para
estes avisos e o próprio usuário o remove. Regras:

- Só manutenção e administrador têm e-mail; o papel usuario é recusado em tudo.
- O endereço é visto e alterado só pelo dono. O administrador vê o endereço na tela do
  usuário e pode desligar as notificações dele, mas nunca grava nem confirma o endereço
  de outra pessoa.
- Confirmação por código de 6 dígitos (``secrets``); grava-se só o HMAC-SHA256 do código
  (segredo OS_HMAC_SEGREDO), preso ao usuário e ao endereço. Vale 15 minutos; 5 erros
  exigem código novo; um código novo no máximo a cada 60 segundos e 5 por hora.
- Endereço não confirmado nunca recebe aviso. Trocar o endereço apaga a confirmação e
  desliga as notificações.
- O aviso de nova solicitação é gravado na fila (``email_fila``) na mesma transação da
  OS; nada fala com o SMTP durante o pedido (services/fila_email.py envia).
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from osapp.db import sessao
from osapp.models import EmailFila, UsuarioNotificacao
from osapp.models.notificacao import (
    FILA_PENDENTE,
    TIPO_CODIGO,
    TIPO_NOVA_SOLICITACAO,
    URGENCIAS_MINIMAS,
)
from osapp.repositories import EmailFilaRepo, NotificacaoRepo, UsuarioRepo
from osapp.services import email_mensagem, protecao_login, relogio
from osapp.services.auth import PAPEL_ADMIN, PAPEL_MANUTENCAO, Ator, carregar_ator
from osapp.services.erros import ErroNaoEncontrado, ErroPermissao, ErroValidacao
from osapp.services.permissoes import exigir_admin, pode_acessar_filial_do_papel

logger = logging.getLogger(__name__)

VARIAVEL_BASE_URL = "OS_BASE_URL"

CODIGO_DIGITOS = 6
CODIGO_VALIDADE = timedelta(minutes=15)
CODIGO_MAX_TENTATIVAS = 5
CODIGO_INTERVALO = timedelta(seconds=60)
CODIGO_JANELA = timedelta(hours=1)
CODIGO_MAX_POR_JANELA = 5

# Ordem das urgências (a mesma de services/ordens.NIVEIS).
ORDEM_URGENCIA = {"baixa": 0, "media": 1, "alta": 2, "emergencial": 3}
PAPEIS_COM_EMAIL = (PAPEL_MANUTENCAO, PAPEL_ADMIN)

MSG_SEM_EMAIL = "Cadastre e confirme um e-mail antes."
MSG_NAO_CONFIRMADO = "Confirme o e-mail antes de ativar as notificações."
MSG_AGUARDE = "Aguarde um minuto antes de pedir outro código."
MSG_LIMITE_HORA = "Limite de códigos por hora atingido. Tente mais tarde."
MSG_SEM_CODIGO = "Peça um código primeiro."
MSG_CODIGO_EXPIRADO = "O código expirou. Peça um novo."
MSG_CODIGO_BLOQUEADO = "Muitas tentativas erradas. Peça um novo código."
MSG_CODIGO_ERRADO = "Código incorreto."
MSG_CODIGO_FORMATO = "Digite os 6 números do código."
MSG_JA_CONFIRMADO = "Este e-mail já está confirmado."
MSG_URGENCIA = "Escolha uma opção."


# --- Modelos de leitura ------------------------------------------------------------------


@dataclass(frozen=True)
class MinhasNotificacoes:
    email: str | None
    confirmado_em: datetime | None
    notificacoes_ativas: bool
    urgencia_minima: str
    codigo_pendente: bool  # há um código válido aguardando digitação


@dataclass(frozen=True)
class NotificacoesDoUsuario:
    """O que o administrador vê na tela de um usuário."""

    disponivel: bool  # o papel do usuário admite e-mail
    email: str | None
    confirmado_em: datetime | None
    notificacoes_ativas: bool
    urgencia_minima: str


# --- Apoio ---------------------------------------------------------------------------------


def _exigir_papel_com_email(ator: Ator) -> None:
    if ator.papel not in PAPEIS_COM_EMAIL:
        raise ErroPermissao()


def _hash_codigo(usuario_id: int, email: str, codigo: str) -> str:
    texto = f"codigo-email:{usuario_id}:{email}:{codigo}"
    return hmac.new(protecao_login.segredo(), texto.encode("utf-8"), "sha256").hexdigest()


def _limpar_codigo(n: UsuarioNotificacao) -> None:
    n.codigo_hash = None
    n.codigo_expira_em = None
    n.codigo_tentativas = 0


def _codigo_valido(n: UsuarioNotificacao, agora: datetime) -> bool:
    return (
        n.codigo_hash is not None
        and n.codigo_expira_em is not None
        and agora < n.codigo_expira_em
        and n.codigo_tentativas < CODIGO_MAX_TENTATIVAS
    )


def _minhas(n: UsuarioNotificacao | None, agora: datetime) -> MinhasNotificacoes:
    if n is None:
        return MinhasNotificacoes(None, None, False, URGENCIAS_MINIMAS[0], False)
    return MinhasNotificacoes(
        email=n.email,
        confirmado_em=n.email_confirmado_em,
        notificacoes_ativas=n.notificacoes_ativas,
        urgencia_minima=n.urgencia_minima,
        codigo_pendente=_codigo_valido(n, agora),
    )


def _registro(s: Session, usuario_id: int) -> UsuarioNotificacao:
    repo = NotificacaoRepo(s)
    n = repo.obter_para_alterar(usuario_id)
    if n is None:
        n = repo.adicionar(UsuarioNotificacao(usuario_id=usuario_id))
    return n


def _trocar_endereco(s: Session, n: UsuarioNotificacao, email: str | None) -> None:
    """Novo endereço (ou nenhum): apaga a confirmação, desliga as notificações e
    cancela o que estava na fila para este usuário."""
    n.email = email
    n.email_confirmado_em = None
    n.notificacoes_ativas = False
    _limpar_codigo(n)
    EmailFilaRepo(s).cancelar_pendentes(EmailFila.usuario_id == n.usuario_id)


# --- Perfil (o próprio usuário) ------------------------------------------------------


def obter_minhas(ator_id: int) -> MinhasNotificacoes:
    ator = carregar_ator(ator_id)
    _exigir_papel_com_email(ator)
    with sessao() as s:
        return _minhas(NotificacaoRepo(s).obter(ator.usuario_id), relogio.agora())


def enviar_codigo(ator_id: int, email: object) -> MinhasNotificacoes:
    """Grava o endereço (se mudou) e põe um código novo na fila de envio.

    Os limites contam por usuário, qualquer que seja o endereço: o app não pode virar
    ferramenta para mandar e-mail a endereços quaisquer.
    """
    ator = carregar_ator(ator_id)
    _exigir_papel_com_email(ator)
    endereco = email_mensagem.normalizar_email(email)
    if endereco is None:
        raise ErroValidacao("email", email_mensagem.MSG_EMAIL_INVALIDO)
    with sessao() as s:
        agora = relogio.agora()
        n = _registro(s, ator.usuario_id)
        if n.email == endereco and n.email_confirmado_em is not None:
            raise ErroValidacao("email", MSG_JA_CONFIRMADO)
        if n.codigo_enviado_em is not None and agora - n.codigo_enviado_em < CODIGO_INTERVALO:
            raise ErroValidacao("email", MSG_AGUARDE)
        if n.codigo_janela_inicio is None or agora - n.codigo_janela_inicio >= CODIGO_JANELA:
            n.codigo_janela_inicio = agora
            n.codigo_envios_janela = 0
        if n.codigo_envios_janela >= CODIGO_MAX_POR_JANELA:
            raise ErroValidacao("email", MSG_LIMITE_HORA)
        if n.email != endereco:
            _trocar_endereco(s, n, endereco)
        else:
            # Mesmo endereço, código novo: o anterior (e o e-mail dele na fila) perde valor.
            EmailFilaRepo(s).cancelar_pendentes(
                EmailFila.usuario_id == n.usuario_id, EmailFila.tipo == TIPO_CODIGO
            )
        codigo = f"{secrets.randbelow(10**CODIGO_DIGITOS):0{CODIGO_DIGITOS}d}"
        n.codigo_hash = _hash_codigo(n.usuario_id, endereco, codigo)
        n.codigo_expira_em = agora + CODIGO_VALIDADE
        n.codigo_tentativas = 0
        n.codigo_enviado_em = agora
        n.codigo_envios_janela += 1
        linha = EmailFilaRepo(s).adicionar(
            EmailFila(
                tipo=TIPO_CODIGO,
                destinatario=endereco,
                assunto=email_mensagem.ASSUNTO_CODIGO,
                corpo=email_mensagem.corpo_codigo(
                    codigo, int(CODIGO_VALIDADE.total_seconds() // 60)
                ),
                status=FILA_PENDENTE,
                proxima_tentativa_em=agora,
                criado_em=agora,
                usuario_id=n.usuario_id,
            )
        )
        logger.info(
            "Código de confirmação na fila: linha=%s usuario_id=%s destino=%s.",
            linha.id,
            n.usuario_id,
            email_mensagem.mascarar(endereco),
        )
        return _minhas(n, agora)


def confirmar_codigo(ator_id: int, codigo: object) -> MinhasNotificacoes:
    ator = carregar_ator(ator_id)
    _exigir_papel_com_email(ator)
    texto = codigo.strip() if isinstance(codigo, str) else ""
    if len(texto) != CODIGO_DIGITOS or not texto.isascii() or not texto.isdigit():
        raise ErroValidacao("codigo", MSG_CODIGO_FORMATO)
    erro: str | None = None
    with sessao() as s:
        agora = relogio.agora()
        n = NotificacaoRepo(s).obter_para_alterar(ator.usuario_id)
        if n is None or n.email is None or n.codigo_hash is None:
            erro = MSG_SEM_CODIGO
        elif n.codigo_expira_em is None or agora >= n.codigo_expira_em:
            erro = MSG_CODIGO_EXPIRADO
        elif n.codigo_tentativas >= CODIGO_MAX_TENTATIVAS:
            erro = MSG_CODIGO_BLOQUEADO
        elif not hmac.compare_digest(n.codigo_hash, _hash_codigo(n.usuario_id, n.email, texto)):
            n.codigo_tentativas += 1  # gravado: o erro é levantado depois do commit
            restantes = CODIGO_MAX_TENTATIVAS - n.codigo_tentativas
            erro = (
                MSG_CODIGO_BLOQUEADO
                if restantes <= 0
                else f"{MSG_CODIGO_ERRADO} Restam {restantes} tentativa(s)."
            )
        else:
            n.email_confirmado_em = agora
            _limpar_codigo(n)
            EmailFilaRepo(s).cancelar_pendentes(
                EmailFila.usuario_id == n.usuario_id, EmailFila.tipo == TIPO_CODIGO
            )
            logger.info("E-mail confirmado: usuario_id=%s.", n.usuario_id)
            resultado = _minhas(n, agora)
    if erro is not None:
        raise ErroValidacao("codigo", erro)
    return resultado


def definir_notificacoes(ator_id: int, ativas: object) -> MinhasNotificacoes:
    ator = carregar_ator(ator_id)
    _exigir_papel_com_email(ator)
    if not isinstance(ativas, bool):
        raise ErroValidacao("notificacoes_ativas", "Valor inválido.")
    with sessao() as s:
        agora = relogio.agora()
        n = NotificacaoRepo(s).obter_para_alterar(ator.usuario_id)
        if ativas and (n is None or n.email is None):
            raise ErroValidacao("notificacoes_ativas", MSG_SEM_EMAIL)
        if ativas and n.email_confirmado_em is None:
            raise ErroValidacao("notificacoes_ativas", MSG_NAO_CONFIRMADO)
        if n is not None:
            n.notificacoes_ativas = ativas
        return _minhas(n, agora)


def definir_urgencia_minima(ator_id: int, valor: object) -> MinhasNotificacoes:
    ator = carregar_ator(ator_id)
    _exigir_papel_com_email(ator)
    if valor not in URGENCIAS_MINIMAS:
        raise ErroValidacao("urgencia_minima", MSG_URGENCIA)
    with sessao() as s:
        n = _registro(s, ator.usuario_id)
        n.urgencia_minima = valor
        return _minhas(n, relogio.agora())


def remover_email(ator_id: int) -> MinhasNotificacoes:
    """Apaga o endereço, a confirmação e o código, desliga as notificações e cancela o
    que estava pendente na fila para este usuário."""
    ator = carregar_ator(ator_id)
    _exigir_papel_com_email(ator)
    with sessao() as s:
        n = NotificacaoRepo(s).obter_para_alterar(ator.usuario_id)
        if n is not None:
            _trocar_endereco(s, n, None)
            n.codigo_enviado_em = None
            logger.info("E-mail removido pelo próprio usuário: usuario_id=%s.", n.usuario_id)
        return _minhas(n, relogio.agora())


# --- Administrador -----------------------------------------------------------------------


def obter_de_usuario(ator_id: int, usuario_id: object) -> NotificacoesDoUsuario:
    ator = carregar_ator(ator_id)
    exigir_admin(ator)
    with sessao() as s:
        usuario = UsuarioRepo(s).obter(usuario_id) if isinstance(usuario_id, int) else None
        if usuario is None:
            raise ErroNaoEncontrado()
        n = NotificacaoRepo(s).obter(usuario.id)
        disponivel = usuario.papel in PAPEIS_COM_EMAIL
        if n is None:
            return NotificacoesDoUsuario(disponivel, None, None, False, URGENCIAS_MINIMAS[0])
        return NotificacoesDoUsuario(
            disponivel, n.email, n.email_confirmado_em, n.notificacoes_ativas, n.urgencia_minima
        )


def desativar_de_usuario(ator_id: int, usuario_id: object) -> NotificacoesDoUsuario:
    """O administrador só desliga; não grava nem confirma endereço de outra pessoa."""
    ator = carregar_ator(ator_id)
    exigir_admin(ator)
    with sessao() as s:
        usuario = UsuarioRepo(s).obter(usuario_id) if isinstance(usuario_id, int) else None
        if usuario is None:
            raise ErroNaoEncontrado()
        n = NotificacaoRepo(s).obter_para_alterar(usuario.id)
        if n is not None and n.notificacoes_ativas:
            n.notificacoes_ativas = False
            logger.info(
                "Notificações desligadas pelo administrador: usuario_id=%s autor_id=%s.",
                usuario.id,
                ator.usuario_id,
            )
    return obter_de_usuario(ator_id, usuario_id)


# --- Gatilho: nova solicitação ---------------------------------------------------------


def recebe(
    papel: str,
    filial_usuario: int,
    urgencia_minima: str,
    filial_os: int,
    urgencia_os: str,
) -> bool:
    """Regra de destinatário (além de ativo, confirmado e com notificações ligadas)."""
    if papel not in PAPEIS_COM_EMAIL:
        return False
    if not pode_acessar_filial_do_papel(papel, filial_usuario, filial_os):
        return False
    return ORDEM_URGENCIA.get(urgencia_os, -1) >= ORDEM_URGENCIA[urgencia_minima]


def enfileirar_nova_solicitacao(
    s: Session, dados: email_mensagem.DadosSolicitacao, filial_id: int, solicitante_id: int
) -> int:
    """Uma linha por destinatário, na sessão (transação) da própria OS. Nunca fala com
    o SMTP. O endereço é copiado para a linha neste instante. Devolve quantas linhas."""
    agora = relogio.agora()
    base_url = os.environ.get(VARIAVEL_BASE_URL, "").strip() or None
    assunto = email_mensagem.assunto_nova_solicitacao(
        dados.filial_codigo, dados.urgencia, dados.titulo
    )
    corpo = email_mensagem.corpo_nova_solicitacao(dados, base_url)
    fila = EmailFilaRepo(s)
    total = 0
    for usuario, n in NotificacaoRepo(s).candidatos(PAPEIS_COM_EMAIL):
        if usuario.id == solicitante_id:
            continue
        if not recebe(
            usuario.papel, usuario.filial_id, n.urgencia_minima, filial_id, dados.urgencia
        ):
            continue
        fila.adicionar(
            EmailFila(
                tipo=TIPO_NOVA_SOLICITACAO,
                destinatario=n.email,
                assunto=assunto,
                corpo=corpo,
                status=FILA_PENDENTE,
                proxima_tentativa_em=agora,
                criado_em=agora,
                os_id=dados.os_id,
                usuario_id=usuario.id,
            )
        )
        total += 1
    if total:
        logger.info("Aviso de nova solicitação na fila: os_id=%s linhas=%s.", dados.os_id, total)
    return total
