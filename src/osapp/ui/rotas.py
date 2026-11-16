"""Tabela central de rotas. Módulo puro (sem Flet)."""

from __future__ import annotations

import re

LOGIN = "/login"
HOME = "/"
OS_NOVA = "/os/nova"

# nome da tela -> padrão do caminho. A ordem importa: /os/nova antes de /os/{id}.
TABELA: dict[str, re.Pattern[str]] = {
    "login": re.compile(r"^/login$"),
    "home": re.compile(r"^/$"),
    "os_nova": re.compile(r"^/os/nova$"),
    "os_detalhe": re.compile(r"^/os/(?P<os_id>[1-9]\d{0,17})$"),
    "os_editar": re.compile(r"^/os/(?P<os_id>[1-9]\d{0,17})/editar$"),
    "os_concluir": re.compile(r"^/os/(?P<os_id>[1-9]\d{0,17})/concluir$"),
}


def rota_os(os_id: int) -> str:
    return f"/os/{os_id}"


def rota_editar(os_id: int) -> str:
    return f"/os/{os_id}/editar"


def rota_concluir(os_id: int) -> str:
    return f"/os/{os_id}/concluir"


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
    if nome in ("os_nova", "os_detalhe"):
        return HOME
    if nome in ("os_editar", "os_concluir"):
        return rota_os(params["os_id"])
    return None
