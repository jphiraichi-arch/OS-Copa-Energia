"""Destinos da barra inferior por papel. Módulo puro (sem Flet).

A interface só mostra caminhos; quem autoriza cada ação é o serviço. Esconder
'Relatórios' é conveniência: o serviço do relatório já recusa o papel usuario.
"""

from __future__ import annotations

from dataclasses import dataclass

from osapp.ui import rotas, textos


@dataclass(frozen=True)
class Destino:
    chave: str  # nome do ícone em ui/app.py
    rotulo: str
    rota: str


ORDENS = Destino("ordens", textos.NAVEGACAO_ORDENS, rotas.HOME)
RELATORIOS = Destino("relatorios", textos.NAVEGACAO_RELATORIOS, rotas.RELATORIOS)
PERFIL = Destino("perfil", textos.NAVEGACAO_PERFIL, rotas.PERFIL)


def nova_os(papel: str) -> Destino:
    """'Nova OS': Nova Solicitação para o usuario; Nova Ordem de Serviço para os demais."""
    rota = rotas.SOLICITACAO_NOVA if papel == "usuario" else rotas.OS_NOVA
    return Destino("nova_os", textos.NAVEGACAO_NOVA_OS, rota)


def destinos(papel: str) -> tuple[Destino, ...]:
    """Nova OS · Ordens · Relatórios (manutenção e administrador) · Perfil.

    Papel desconhecido: só Ordens e Perfil."""
    if papel == "usuario":
        return (nova_os(papel), ORDENS, PERFIL)
    if papel in ("manutencao", "admin"):
        return (nova_os(papel), ORDENS, RELATORIOS, PERFIL)
    return (ORDENS, PERFIL)


def ve_relatorios(papel: str) -> bool:
    """Atalhos para Relatórios: manutenção e administrador (o usuario não tem)."""
    return papel in ("manutencao", "admin")


def destino_ativo(papel: str, rota: str) -> int | None:
    """Índice do destino da barra que corresponde à rota (o pai, para subtelas)."""
    caminho = rotas.normalizar(rota)
    lista = destinos(papel)
    for indice, d in enumerate(lista):
        if d.rota == caminho:
            return indice
    pai = rotas.secao_da_rota(caminho)
    for indice, d in enumerate(lista):
        if d.rota == pai:
            return indice
    return None
