"""Barra inferior própria (prompt 41).

O ft.NavigationBar do Flet 1.1 não tem largura máxima nem alinhamento dos itens
(https://flet.dev/docs/controls/navigationbar): numa tela larga os destinos se espalham
pela janela inteira. Esta barra tem os mesmos destinos, o selo de 'Ordens', o destino
selecionado (fundo laranja, ícone cheio e rótulo em negrito: a cor nunca é o único
sinal), alvos de toque de 48 px ou mais e rótulo acessível em cada ícone. O fundo ocupa a
largura toda; os itens ficam centralizados em ``theme.LARGURA_MAX_CONTEUDO``.

Ela é posta DEPOIS da área de conteúdo rolável, na mesma coluna: o conteúdo termina acima
da barra e nunca fica por baixo dela.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from osapp.ui import theme


def altura(largo: bool) -> int:
    """Função pura (testada): ~60 px na tela larga; 80 px no celular, como antes."""
    return theme.ALTURA_BARRA_LARGA if largo else theme.ALTURA_BARRA_CELULAR


class BarraInferior:
    """``destinos``: lista de (rótulo, ícone, ícone selecionado). ``ao_escolher(indice)``."""

    def __init__(
        self,
        destinos: list[tuple[str, ft.IconData, ft.IconData]],
        ativo: int | None,
        ao_escolher: Callable[[int], None],
        largo: bool,
        selos: dict[int, str] | None = None,
    ) -> None:
        self.destinos = destinos
        self.ativo = ativo
        self.ao_escolher = ao_escolher
        self.largo = largo
        self.selos = dict(selos or {})
        self.linha = ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_AROUND,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0,
        )
        self.controle = ft.Container(
            bgcolor=theme.COR_BARRA,
            height=altura(largo),
            alignment=ft.Alignment.CENTER,
            content=ft.Container(max_width=theme.LARGURA_MAX_CONTEUDO, content=self.linha),
        )
        self._montar()

    def definir_selo(self, indice: int, texto: str | None) -> None:
        if texto:
            self.selos[indice] = texto
        else:
            self.selos.pop(indice, None)
        self._montar()
        try:
            self.controle.update()
        except RuntimeError:
            pass  # ainda não está na página

    def _montar(self) -> None:
        self.linha.controls = [
            self._item(i, rotulo, icone, icone_sel)
            for i, (rotulo, icone, icone_sel) in enumerate(self.destinos)
        ]

    def _item(self, indice: int, rotulo: str, icone, icone_sel) -> ft.Control:
        selecionado = indice == self.ativo
        selo = self.selos.get(indice)
        icone_ctl = ft.Icon(
            icone_sel if selecionado else icone,
            color=theme.COR_SOBRE_DESTAQUE if selecionado else theme.COR_ICONE_BARRA,
            semantics_label=rotulo,
            badge=ft.Badge(label=selo, bgcolor=theme.COR_CARTAO, text_color=theme.COR_TITULO)
            if selo
            else None,
        )
        return ft.Container(
            expand=True,
            height=max(theme.ALVO_TOQUE_MIN, altura(self.largo)),
            ink=True,
            tooltip=rotulo,
            on_click=lambda _e, i=indice: self.ao_escolher(i),
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [
                    ft.Container(
                        content=icone_ctl,
                        bgcolor=theme.COR_DESTAQUE if selecionado else None,
                        border_radius=theme.RAIO_CHIP,
                        padding=ft.Padding.symmetric(horizontal=16, vertical=2),
                    ),
                    ft.Text(
                        rotulo,
                        color=theme.COR_ICONE_BARRA,
                        size=theme.FONTE_PEQUENA,
                        weight=ft.FontWeight.BOLD if selecionado else None,
                        no_wrap=True,
                    ),
                ],
                spacing=2,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
        )
