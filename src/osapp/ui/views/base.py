"""Contrato comum das telas."""

from __future__ import annotations

import flet as ft


class Tela:
    """Uma tela: um controle de conteúdo e, opcionalmente, uma carga de dados assíncrona."""

    conteudo: ft.Control

    async def carregar(self) -> None:
        """Busca os dados depois de a tela aparecer. Por padrão, nada."""

    def tem_alteracoes(self) -> bool:
        """True se sair da tela perderia dados digitados."""
        return False
