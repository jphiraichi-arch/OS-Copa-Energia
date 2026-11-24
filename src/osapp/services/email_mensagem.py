"""Texto dos e-mails e validação de endereço (prompt 32). Funções puras, testadas.

- Só texto puro (UTF-8), montado com ``email.message.EmailMessage``.
- Texto digitado por usuários (título, descrição, nomes) só entra no Assunto (limpo de
  CR, LF e de todo caractere de controle, espaços colapsados, no máximo 150 caracteres)
  e no corpo. Nenhum outro cabeçalho recebe texto de usuário.
- Nunca entram custos, previsto, realizado, prioridade, executor nem o histórico.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime
from zoneinfo import ZoneInfo

EMAIL_MAX = 254
LOCAL_MAX = 64
ASSUNTO_MAX = 150
FUSO_EMAIL = "America/Sao_Paulo"

ROTULO_URGENCIA = {
    "baixa": "BAIXA",
    "media": "MÉDIA",
    "alta": "ALTA",
    "emergencial": "EMERGENCIAL",
}
NOME_URGENCIA = {"baixa": "Baixa", "media": "Média", "alta": "Alta", "emergencial": "Emergencial"}

RODAPE_NOTIFICACAO = "Você recebe este aviso porque ativou as notificações no seu perfil."
ASSUNTO_CODIGO = "Código de confirmação do e-mail"

MSG_EMAIL_INVALIDO = "Informe um e-mail válido, por exemplo nome@empresa.com.br."

_ESPACOS = re.compile(r"\s+")


# --- Endereço --------------------------------------------------------------------------


def _tem_controle(texto: str) -> bool:
    return any(unicodedata.category(c).startswith("C") for c in texto)


def normalizar_email(valor: object) -> str | None:
    """Endereço normalizado, ou None se inválido.

    Verificação simples e documentada (não é um analisador completo da RFC 5322):
    sem espaços nas pontas; até 254 caracteres; exatamente um '@'; parte local com 1 a
    64 caracteres; domínio com pelo menos um ponto, sem pontos nas pontas nem dois
    seguidos; nenhum espaço nem caractere de controle (categoria Unicode C*). O domínio
    vai para minúsculas; a parte local fica como digitada.
    """
    if not isinstance(valor, str):
        return None
    texto = valor.strip()
    if not texto or len(texto) > EMAIL_MAX or texto.count("@") != 1:
        return None
    if _tem_controle(texto) or any(c.isspace() for c in texto):
        return None
    local, dominio = texto.split("@")
    dominio = dominio.lower()
    if not (1 <= len(local) <= LOCAL_MAX) or not dominio or "." not in dominio:
        return None
    if dominio.startswith(".") or dominio.endswith(".") or ".." in dominio:
        return None
    if any(c in local + dominio for c in '<>(),;:"[]\\'):
        return None
    return f"{local}@{dominio}"


def mascarar(email: str | None) -> str:
    """'joana@empresa.com.br' -> 'j***@empresa.com.br' (para logs e telas de admin)."""
    if not email or "@" not in email:
        return "***"
    local, dominio = email.rsplit("@", 1)
    return f"{local[:1]}***@{dominio}"


# --- Assunto ---------------------------------------------------------------------------


def limpar_linha(texto: object) -> str:
    """Troca todo caractere de controle (categorias Unicode C*: CR, LF, TAB, NUL...) e os
    separadores de linha e de parágrafo (Zl, Zp) por espaço e colapsa os espaços."""
    if texto is None:
        return ""
    bruto = "".join(
        " "
        if unicodedata.category(c).startswith("C") or unicodedata.category(c) in ("Zl", "Zp")
        else c
        for c in str(texto)
    )
    return _ESPACOS.sub(" ", bruto).strip()


def assunto_nova_solicitacao(codigo_filial: str, urgencia: str, titulo: str) -> str:
    partes = (
        limpar_linha(codigo_filial),
        limpar_linha(ROTULO_URGENCIA.get(urgencia, urgencia)),
        limpar_linha(titulo),
    )
    return f"[{partes[0]}] [{partes[1]}] {partes[2]}"[:ASSUNTO_MAX].rstrip()


# --- Corpo -----------------------------------------------------------------------------


@dataclass(frozen=True)
class DadosSolicitacao:
    """Só o que pode ir no e-mail. De propósito não há campo de custo, previsto,
    realizado, prioridade, executor nem histórico."""

    os_id: int
    numero: str
    filial_codigo: str
    filial_nome: str
    titulo: str
    urgencia: str
    descricao: str
    solicitante: str
    aberta_em: datetime


def data_hora_brasilia(instante: datetime) -> str:
    local = instante.astimezone(ZoneInfo(FUSO_EMAIL))
    return local.strftime("%d/%m/%Y %H:%M")


def link_os(base_url: str | None, os_id: int) -> str | None:
    if not base_url:
        return None
    return f"{base_url.rstrip('/')}/os/{os_id}"


def corpo_nova_solicitacao(dados: DadosSolicitacao, base_url: str | None) -> str:
    link = link_os(base_url, dados.os_id)
    linhas = [
        "Nova solicitação de manutenção.",
        "",
        f"Número: {dados.numero}",
        f"Filial: {limpar_linha(dados.filial_codigo)} - {limpar_linha(dados.filial_nome)}",
        f"Título: {limpar_linha(dados.titulo)}",
        f"Urgência: {NOME_URGENCIA.get(dados.urgencia, dados.urgencia)}",
        f"Solicitante: {limpar_linha(dados.solicitante)}",
        f"Aberta em: {data_hora_brasilia(dados.aberta_em)} (horário de Brasília)",
        "",
        "Descrição:",
        (dados.descricao or "").replace("\r\n", "\n").replace("\r", "\n").strip() or "-",
        "",
        f"Abrir a OS: {link}" if link else f"Abra a OS {dados.numero} no Sistema de OS.",
        "",
        RODAPE_NOTIFICACAO,
    ]
    return "\n".join(linhas) + "\n"


def corpo_codigo(codigo: str, validade_min: int) -> str:
    return (
        f"Seu código de confirmação do e-mail no Sistema de OS é: {codigo}\n"
        "\n"
        f"Ele vale por {validade_min} minutos.\n"
        "\n"
        "Se você não pediu este código, ignore esta mensagem.\n"
    )


# --- Mensagem --------------------------------------------------------------------------


def dominio_remetente(remetente: str) -> str:
    return remetente.rsplit("@", 1)[-1] if "@" in remetente else "localhost"


def montar_mensagem(
    linha_id: int,
    remetente: str,
    destinatario: str,
    assunto: str,
    corpo: str,
    agora: datetime,
) -> EmailMessage:
    """Mensagem pronta para o SMTP. Cabeçalhos: From, To, Subject, Date, Message-ID e os
    de MIME. O Message-ID é estável (vem do id da linha): o mesmo e-mail reenviado depois
    de uma queda tem o mesmo Message-ID e o cliente de e-mail pode reconhecer a cópia."""
    msg = EmailMessage()
    msg["From"] = remetente
    msg["To"] = destinatario
    msg["Subject"] = limpar_linha(assunto)[:ASSUNTO_MAX]
    msg["Date"] = format_datetime(agora)
    msg["Message-ID"] = f"<os-email-{linha_id}@{dominio_remetente(remetente)}>"
    msg.set_content(corpo, subtype="plain", charset="utf-8")
    return msg
