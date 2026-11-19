"""Destinos da navegação principal por papel. Módulo puro (sem Flet).

A interface só mostra caminhos; quem autoriza cada ação é o serviço.
"""

from __future__ import annotations

from dataclasses import dataclass

from osapp.ui import rotas, textos


@dataclass(frozen=True)
class Destino:
    chave: str  # nome do ícone em ui/app.py
    rotulo: str  # barra inferior (celular)
    rotulo_trilho: str  # trilho lateral (telas largas)
    rota: str


ORDENS = Destino("ordens", textos.NAVEGACAO_ORDENS, textos.TRILHO_ORDENS, rotas.HOME)
NOVA_ORDEM = Destino(
    "nova_ordem", textos.NAVEGACAO_NOVA_ORDEM, textos.TRILHO_NOVA_ORDEM, rotas.OS_NOVA
)
NOVA_SOLICITACAO = Destino(
    "nova_solicitacao",
    textos.NAVEGACAO_NOVA_SOLICITACAO,
    textos.TRILHO_NOVA_SOLICITACAO,
    rotas.SOLICITACAO_NOVA,
)


def destinos(papel: str) -> tuple[Destino, ...]:
    """usuario: Ordens e Nova Solicitação. manutencao: Ordens e Nova Ordem de Serviço.
    admin: os da manutenção e Nova Solicitação. Papel desconhecido: só Ordens."""
    if papel == "usuario":
        return (ORDENS, NOVA_SOLICITACAO)
    if papel == "manutencao":
        return (ORDENS, NOVA_ORDEM)
    if papel == "admin":
        return (ORDENS, NOVA_ORDEM, NOVA_SOLICITACAO)
    return (ORDENS,)


def ve_relatorios(papel: str) -> bool:
    """Entrada 'Relatórios' no menu: manutenção e administrador (o usuario não tem)."""
    return papel in ("manutencao", "admin")
