"""Estado da sessão (mantido no servidor, por sessão do navegador) e guarda de rotas.

Módulo puro (sem Flet). Nada daqui vai para o armazenamento do cliente: nem senha,
nem hash, nem token.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from osapp.ui import rotas

MENSAGEM_SESSAO_EXPIRADA = "Sessão expirada. Entre novamente."


@dataclass
class SessaoUI:
    timeout_min: int
    ator_id: int | None = None
    ultima_atividade: datetime | None = None
    # Dados de exibição do cabeçalho, copiados do Ator no login.
    nome: str = ""
    filial_id: int | None = None
    filial_codigo: str = ""
    is_admin: bool = False
    # Rota pedida antes do login (link direto), para onde ir depois de entrar.
    rota_pendente: str | None = None
    # Mensagem a mostrar uma vez na tela de login.
    mensagem_login: str | None = None


def expirada(sessao: SessaoUI, agora: datetime) -> bool:
    """True se há usuário na sessão e o tempo sem atividade passou do limite."""
    if sessao.ator_id is None or sessao.ultima_atividade is None:
        return False
    return agora - sessao.ultima_atividade >= timedelta(minutes=sessao.timeout_min)


def autenticada(sessao: SessaoUI, agora: datetime) -> bool:
    return sessao.ator_id is not None and not expirada(sessao, agora)


def decidir_rota(rota: str | None, sessao: SessaoUI, agora: datetime) -> str:
    """Rota que deve ser mostrada. Função pura, chamada a cada mudança de rota.

    - Sem login (ou com a sessão expirada): /login.
    - Com login e em /login: a rota pedida antes do login, ou /.
    - Rota desconhecida: /.
    """
    if not autenticada(sessao, agora):
        return rotas.LOGIN
    destino = rotas.normalizar(rota)
    if destino == rotas.LOGIN:
        return rotas.normalizar(sessao.rota_pendente) if sessao.rota_pendente else rotas.HOME
    return destino


def iniciar(sessao: SessaoUI, ator, agora: datetime) -> None:
    """Registra o login. ``ator`` é o Ator devolvido pelo serviço de autenticação."""
    sessao.ator_id = ator.usuario_id
    sessao.nome = ator.nome
    sessao.filial_id = ator.filial_id
    sessao.filial_codigo = ator.filial_codigo
    sessao.is_admin = ator.is_admin
    sessao.ultima_atividade = agora
    sessao.mensagem_login = None


def encerrar(sessao: SessaoUI, mensagem: str | None = None) -> None:
    """Limpa a sessão (logout ou expiração)."""
    sessao.ator_id = None
    sessao.ultima_atividade = None
    sessao.nome = ""
    sessao.filial_id = None
    sessao.filial_codigo = ""
    sessao.is_admin = False
    sessao.rota_pendente = None
    sessao.mensagem_login = mensagem


def registrar_atividade(sessao: SessaoUI, agora: datetime) -> None:
    if sessao.ator_id is not None:
        sessao.ultima_atividade = agora


def aplicar_navegacao(rota: str | None, sessao: SessaoUI, agora: datetime) -> str:
    """Decide a rota e atualiza a sessão: expiração, link direto e atividade."""
    if expirada(sessao, agora):
        encerrar(sessao, MENSAGEM_SESSAO_EXPIRADA)
    destino = decidir_rota(rota, sessao, agora)
    if sessao.ator_id is None:
        pedida = rotas.normalizar(rota)
        if pedida != rotas.LOGIN and rotas.resolver(rota) is not None:
            sessao.rota_pendente = pedida  # lembrada até o login
    else:
        sessao.rota_pendente = None
        registrar_atividade(sessao, agora)
    return destino
