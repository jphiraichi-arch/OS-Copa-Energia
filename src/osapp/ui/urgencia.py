"""Textos das opções de urgência (cartões de opção). Módulo de constantes, sem Flet."""

from __future__ import annotations

from osapp.services.ordens import NIVEIS
from osapp.ui import rotulos

SIGNIFICADO: dict[str, str] = {
    "baixa": "Pode aguardar, nada parado",
    "media": "Atrapalha, mas há alternativa",
    "alta": "Prejudica a produção",
    "emergencial": "Equipamento parado ou risco de segurança",
}
assert set(SIGNIFICADO) == set(NIVEIS)


def pill(nivel: str | None) -> str:
    """Texto do StatusPill da seção de urgência: 'URGÊNCIA: ALTA'."""
    return f"URGÊNCIA: {rotulos.nivel(nivel).upper()}" if nivel else "URGÊNCIA: A ESCOLHER"


def opcoes(cores: dict[str, str]) -> list[tuple[str, str, str, str]]:
    """(valor, cor, rótulo, significado) na ordem de NIVEIS, para OpcaoGrupo."""
    return [(n, cores[n], rotulos.nivel(n), SIGNIFICADO[n]) for n in NIVEIS]
