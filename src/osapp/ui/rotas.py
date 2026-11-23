"""Tabela central de rotas. Módulo puro (sem Flet)."""

from __future__ import annotations

import re

LOGIN = "/login"
HOME = "/"
OS_NOVA = "/os/nova"
SOLICITACAO_NOVA = "/solicitacao/nova"
CONFIGURACOES = "/configuracoes"
TROCAR_SENHA = "/trocar-senha"
USUARIOS = "/usuarios"
USUARIO_NOVO = "/usuarios/novo"
RELATORIOS = "/relatorios"
RELATORIO_MENSAL = "/relatorios/mensal"
PERFIL = "/perfil"
ALTERAR_SENHA = "/perfil/senha"

# nome da tela -> padrão do caminho. A ordem importa: /os/nova antes de /os/{id}.
TABELA: dict[str, re.Pattern[str]] = {
    "login": re.compile(r"^/login$"),
    "home": re.compile(r"^/$"),
    "configuracoes": re.compile(r"^/configuracoes$"),
    "trocar_senha": re.compile(r"^/trocar-senha$"),
    "usuarios": re.compile(r"^/usuarios$"),
    "usuario_novo": re.compile(r"^/usuarios/novo$"),
    "usuario": re.compile(r"^/usuarios/(?P<usuario_id>[1-9]\d{0,17})$"),
    "perfil": re.compile(r"^/perfil$"),
    "alterar_senha": re.compile(r"^/perfil/senha$"),
    "relatorios": re.compile(r"^/relatorios$"),
    "relatorios_mensal": re.compile(r"^/relatorios/mensal$"),
    "os_nova": re.compile(r"^/os/nova$"),
    "solicitacao_nova": re.compile(r"^/solicitacao/nova$"),
    "os_detalhe": re.compile(r"^/os/(?P<os_id>[1-9]\d{0,17})$"),
    "os_editar": re.compile(r"^/os/(?P<os_id>[1-9]\d{0,17})/editar$"),
    "os_concluir": re.compile(r"^/os/(?P<os_id>[1-9]\d{0,17})/concluir$"),
    "os_assumir": re.compile(r"^/os/(?P<os_id>[1-9]\d{0,17})/assumir$"),
    "os_solicitacao": re.compile(r"^/os/(?P<os_id>[1-9]\d{0,17})/solicitacao$"),
}


def rota_os(os_id: int) -> str:
    return f"/os/{os_id}"


def rota_editar(os_id: int) -> str:
    return f"/os/{os_id}/editar"


def rota_concluir(os_id: int) -> str:
    return f"/os/{os_id}/concluir"


def rota_usuario(usuario_id: int) -> str:
    return f"/usuarios/{usuario_id}"


def rota_assumir(os_id: int) -> str:
    return f"/os/{os_id}/assumir"


def rota_editar_solicitacao(os_id: int) -> str:
    return f"/os/{os_id}/solicitacao"


def _caminho(rota: str | None) -> str:
    caminho = (rota or "").split("?", 1)[0].split("#", 1)[0].strip()
    if len(caminho) > 1:
        caminho = caminho.rstrip("/")
    return caminho or HOME


def resolver(rota: str | None) -> tuple[str, dict[str, int]] | None:
    """(nome da tela, parâmetros) para uma rota conhecida; None para rota desconhecida."""
    caminho = _caminho(rota)
    for nome, padrao in TABELA.items():
        m = padrao.match(caminho)
        if m:
            return nome, {k: int(v) for k, v in m.groupdict().items()}
    return None


def normalizar(rota: str | None) -> str:
    """Caminho canônico da rota; rota desconhecida vira '/'."""
    return _caminho(rota) if resolver(rota) else HOME


def rota_anterior(rota: str) -> str | None:
    """Tela para onde o botão de voltar leva; None na tela inicial e no login."""
    resolvida = resolver(rota)
    if resolvida is None:
        return None
    nome, params = resolvida
    if nome in ("os_nova", "solicitacao_nova", "os_detalhe", "relatorios", "perfil"):
        return HOME
    if nome == "relatorios_mensal":
        return RELATORIOS
    if nome in ("configuracoes", "alterar_senha", "usuarios"):
        return PERFIL
    if nome in ("usuario_novo", "usuario"):
        return USUARIOS
    if nome in ("os_editar", "os_concluir", "os_assumir", "os_solicitacao"):
        return rota_os(params["os_id"])
    return None


def secao_da_rota(rota: str | None) -> str:
    """Destino da barra inferior a que a rota pertence (para marcá-lo como ativo)."""
    resolvida = resolver(rota)
    if resolvida is None:
        return HOME
    nome = resolvida[0]
    if nome in ("relatorios", "relatorios_mensal"):
        return RELATORIOS
    if nome in ("perfil", "configuracoes", "alterar_senha", "usuarios", "usuario_novo", "usuario"):
        return PERFIL
    if nome in ("os_nova", "solicitacao_nova"):
        return _caminho(rota)
    return HOME
