"""Chips para escolhas pequenas e discretas (tipo, prioridade, filtros de status).

GrupoChips: escolha única (``multipla=False``, com opção de desmarcar se ``opcional``)
ou múltipla. O rótulo sempre aparece e o chip selecionado leva a marca de seleção (não só a cor).
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from osapp.ui import theme


def chip(rotulo: str, selecionado: bool, on_select: Callable[[], None]) -> ft.Chip:
    return ft.Chip(
        label=ft.Text(rotulo, color=theme.COR_TITULO, size=theme.FONTE_SUBTITULO),
        selected=selecionado,
        show_checkmark=True,
        check_color=theme.COR_TITULO,
        bgcolor=theme.COR_CARTAO,
        selected_color=theme.COR_SELECAO_SUAVE,
        height=theme.ALVO_TOQUE_MIN,
        on_select=lambda _e: on_select(),
    )


class GrupoChips:
    """``opcoes``: lista de (valor, rótulo). ``valor``: o valor (única) ou um conjunto
    (múltipla). ``minimo`` (múltipla): quantos precisam ficar marcados."""

    def __init__(
        self,
        opcoes,
        valor=None,
        multipla: bool = False,
        opcional: bool = True,
        minimo: int = 0,
        ao_mudar: Callable[[], None] | None = None,
    ) -> None:
        self.opcoes = list(opcoes)
        self.multipla = multipla
        self.opcional = opcional
        self.minimo = minimo
        self.valor = set(valor or ()) if multipla else valor
        self._ao_mudar = ao_mudar
        self.erro = ft.Text("", color=theme.COR_ERRO, size=theme.FONTE_PEQUENA, visible=False)
        self.linha = ft.Row(wrap=True, spacing=theme.ESPACO_P, run_spacing=theme.ESPACO_P)
        self.controle = ft.Column(
            [self.linha, self.erro],
            spacing=4,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self._montar()

    def _selecionado(self, valor) -> bool:
        return valor in self.valor if self.multipla else valor == self.valor

    def _montar(self) -> None:
        self.linha.controls = [
            chip(rotulo, self._selecionado(valor), lambda v=valor: self.alternar(v))
            for valor, rotulo in self.opcoes
        ]

    def alternar(self, valor) -> None:
        if self.multipla:
            if valor in self.valor and len(self.valor) > self.minimo:
                self.valor.discard(valor)
            else:
                self.valor.add(valor)
        elif valor == self.valor and self.opcional:
            self.valor = None
        else:
            self.valor = valor
        self.marcar_erro(None)
        self._montar()
        self.update()
        if self._ao_mudar:
            self._ao_mudar()

    def definir(self, valor) -> None:
        self.valor = set(valor or ()) if self.multipla else valor
        self._montar()

    def marcar_erro(self, mensagem: str | None) -> None:
        self.erro.value = mensagem or ""
        self.erro.visible = bool(mensagem)

    @property
    def error(self) -> str | None:
        return self.erro.value or None

    @error.setter
    def error(self, mensagem: str | None) -> None:
        self.marcar_erro(mensagem)

    def update(self) -> None:
        try:
            self.controle.update()
        except RuntimeError:
            pass  # ainda não está na página
