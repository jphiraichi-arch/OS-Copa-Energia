"""Seletor do escopo da busca (prompt 22): 'Itens' ou 'Tudo'.

Padrão por tela (decisão de 21/11/2026): Home 'Tudo'; relatório 'Itens'.

Só para manutenção e administrador; quem decide o escopo efetivo é o serviço
(ordens.condicao_busca), que sempre busca só em título e descrição para o papel usuario.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

from osapp.services import ordens
from osapp.ui import theme

ROTULOS = {ordens.ESCOPO_ITENS: "Itens", ordens.ESCOPO_TUDO: "Tudo"}


class SeletorEscopo:
    def __init__(
        self, app, ao_mudar: Callable[[], Awaitable[None]], inicial: str = ordens.ESCOPO_ITENS
    ) -> None:
        if inicial not in ordens.ESCOPOS:
            raise ValueError(f"Escopo desconhecido: {inicial!r}")
        self.app = app
        self.valor = inicial
        self._ao_mudar = ao_mudar
        self.controle = ft.Row(spacing=theme.ESPACO_P, wrap=True)
        self._montar()

    def _montar(self) -> None:
        self.controle.controls = [
            ft.Chip(
                label=ft.Text(rotulo, color=theme.COR_TITULO, size=theme.FONTE_SUBTITULO),
                selected=self.valor == valor,
                show_checkmark=True,
                check_color=theme.COR_TITULO,
                bgcolor=theme.COR_CARTAO,
                selected_color=theme.COR_INDICADOR_NAVEGACAO,
                tooltip=f"Buscar em: {rotulo}",
                on_select=lambda _e, v=valor: self.app.page.run_task(self._escolher, v),
            )
            for valor, rotulo in ROTULOS.items()
        ]

    async def _escolher(self, valor: str) -> None:
        self.valor = valor
        self._montar()
        try:
            self.controle.update()
        except RuntimeError:
            return
        await self._ao_mudar()
