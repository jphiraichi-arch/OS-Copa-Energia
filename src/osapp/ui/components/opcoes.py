"""Cartões de opção para escolhas importantes (OpcaoCard) e o grupo de escolha única.

OpcaoCard: cartão grande com um ponto colorido, o rótulo e uma linha de significado.
Selecionado: borda laranja de destaque, ícone de confirmação e a etiqueta 'SELECIONADO'.
No mínimo 48 px de altura, inteiro tocável, com rótulo acessível (ft.Semantics).
A cor nunca é o único sinal: o rótulo, o ícone e a etiqueta dizem o mesmo.
"""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from osapp.ui import theme

ETIQUETA_SELECIONADO = "SELECIONADO"


def opcao_card(
    cor: str,
    rotulo: str,
    descricao: str,
    selecionado: bool,
    on_select: Callable[[], None] | None = None,
) -> ft.Control:
    etiqueta = ft.Container(
        visible=selecionado,
        bgcolor=theme.COR_DESTAQUE,
        border_radius=theme.RAIO_CHIP,
        padding=ft.Padding.symmetric(horizontal=8, vertical=2),
        content=ft.Text(
            ETIQUETA_SELECIONADO,
            color=theme.COR_SOBRE_DESTAQUE,
            size=theme.FONTE_PEQUENA,
            weight=ft.FontWeight.BOLD,
        ),
    )
    cartao = ft.Container(
        bgcolor=theme.COR_CARTAO,
        border=ft.Border.all(
            3 if selecionado else 1, theme.COR_DESTAQUE if selecionado else theme.COR_CONTORNO
        ),
        border_radius=theme.RAIO_CARTAO,
        padding=ft.Padding.symmetric(horizontal=theme.ESPACO_M, vertical=theme.ESPACO_P + 4),
        ink=True,
        on_click=(lambda _e: on_select()) if on_select else None,
        content=ft.Row(
            [
                ft.Container(width=14, height=14, bgcolor=cor, border_radius=theme.RAIO_CHIP),
                ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    rotulo,
                                    color=theme.COR_TITULO,
                                    size=theme.FONTE_CORPO,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                etiqueta,
                            ],
                            spacing=theme.ESPACO_P,
                            wrap=True,
                        ),
                        ft.Text(descricao, color=theme.COR_SUBTITULO, size=theme.FONTE_SUBTITULO),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.Icon(
                    ft.Icons.CHECK_CIRCLE if selecionado else ft.Icons.RADIO_BUTTON_UNCHECKED,
                    color=theme.COR_DESTAQUE if selecionado else theme.COR_SUBTITULO,
                ),
            ],
            spacing=theme.ESPACO_M,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )
    return ft.Semantics(
        content=cartao, label=f"{rotulo}: {descricao}", selected=selecionado, button=True
    )


class OpcaoGrupo:
    """Escolha única entre OpcaoCards; 2 colunas em telas largas, 1 no celular.

    ``opcoes``: lista de (valor, cor, rótulo, descrição). Também serve de alvo de erro
    para App.chamar (propriedade ``error`` e ``update``).
    """

    def __init__(self, opcoes, valor=None, ao_mudar: Callable[[], None] | None = None) -> None:
        self.opcoes = list(opcoes)
        self.valor = valor
        self._ao_mudar = ao_mudar
        self.erro = ft.Text("", color=theme.COR_ERRO, size=theme.FONTE_PEQUENA, visible=False)
        self.grade = ft.ResponsiveRow(spacing=theme.ESPACO_P, run_spacing=theme.ESPACO_P)
        self.controle = ft.Column(
            [self.grade, self.erro],
            spacing=theme.ESPACO_P,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self._montar()

    def _montar(self) -> None:
        self.grade.controls = [
            ft.Container(
                col={"xs": 12, "md": 6},
                content=opcao_card(
                    cor,
                    rotulo,
                    descricao,
                    valor == self.valor,
                    on_select=lambda v=valor: self.escolher(v),
                ),
            )
            for valor, cor, rotulo, descricao in self.opcoes
        ]

    def escolher(self, valor) -> None:
        self.valor = valor
        self.marcar_erro(None)
        self._montar()
        self.update()
        if self._ao_mudar:
            self._ao_mudar()

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
