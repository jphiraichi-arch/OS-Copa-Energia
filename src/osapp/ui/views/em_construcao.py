"""Tela provisória das rotas cujas telas reais chegam nos próximos prompts."""

from __future__ import annotations

import flet as ft

from osapp.ui import theme
from osapp.ui.components import basicos
from osapp.ui.views.base import Tela


class EmConstrucao(Tela):
    def __init__(self, app, nome_da_tela: str, **_params) -> None:
        self.conteudo = basicos.cartao(
            basicos.coluna(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.CONSTRUCTION, color=theme.COR_DESTAQUE),
                            basicos.titulo(nome_da_tela),
                        ],
                        spacing=theme.ESPACO_P,
                    ),
                    basicos.subtitulo("Em construção"),
                ],
                espaco=theme.ESPACO_P,
            )
        )
