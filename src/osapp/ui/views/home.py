"""Home: lista de ordens de serviço com busca e filtros.

Nenhuma regra de filial ou permissão aqui: os filtros vão para o serviço e a tela
mostra o que ele devolver.
"""

from __future__ import annotations

import flet as ft

from osapp import formatacao
from osapp.services import ordens, status
from osapp.ui import rotas, textos, theme
from osapp.ui.components import basicos
from osapp.ui.views.base import Tela

TODAS_AS_FILIAIS = "todas"


class Home(Tela):
    def __init__(self, app, **_params) -> None:
        self.app = app
        self.filtro_status: str | None = None
        # Para administrador, o filtro começa na própria filial; os demais não escolhem.
        self.filtro_filial: int | None = app.sessao.filial_id if app.sessao.is_admin else None
        self.pagina = 1
        self.itens: list = []

        self.busca = basicos.campo_texto(
            textos.HOME_BUSCA,
            hint_text=textos.HOME_BUSCA_DICA,
            on_submit=self._buscar,
            suffix_icon=ft.IconButton(
                icon=ft.Icons.SEARCH,
                icon_color=theme.COR_BOTAO_PRIMARIO,
                tooltip=textos.HOME_BUSCAR,
                width=theme.ALVO_TOQUE_MIN,
                height=theme.ALVO_TOQUE_MIN,
                on_click=self._buscar,
            ),
        )
        self.chips = ft.Row(wrap=True, spacing=theme.ESPACO_P, run_spacing=theme.ESPACO_P)
        self._montar_chips()
        self.filial = ft.Dropdown(
            label=textos.HOME_FILIAL,
            visible=False,
            expand=True,
            color=theme.COR_TITULO,
            bgcolor=theme.COR_CARTAO,
            filled=True,
            fill_color=theme.COR_CAMPO_FUNDO,
            border_color=theme.COR_CONTORNO,
            border_radius=theme.RAIO_BOTAO,
            label_style=ft.TextStyle(color=theme.COR_SUBTITULO),
            on_select=self._ao_escolher_filial,
        )
        self.atualizar = ft.TextButton(
            content=textos.HOME_ATUALIZAR,
            icon=ft.Icons.REFRESH,
            style=theme.estilo_botao_texto(),
            height=theme.ALVO_TOQUE_MIN,
            on_click=self._recarregar,
        )
        self.lista = basicos.coluna([], espaco=theme.ESPACO_M)
        self.rodape = basicos.coluna([])
        self.conteudo = basicos.coluna(
            [
                basicos.titulo(textos.HOME_TITULO, theme.FONTE_SAUDACAO),
                self.busca,
                self.chips,
                ft.Row(
                    [self.filial, self.atualizar],
                    alignment=ft.MainAxisAlignment.END,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self.lista,
                self.rodape,
            ]
        )

    # --- Filtros ----------------------------------------------------------------------

    def _montar_chips(self) -> None:
        opcoes = [(None, textos.HOME_TODAS), *status.ROTULOS.items()]
        self.chips.controls = [
            ft.Chip(
                label=ft.Text(rotulo, color=theme.COR_TITULO, size=theme.FONTE_SUBTITULO),
                selected=self.filtro_status == valor,
                show_checkmark=True,
                check_color=theme.COR_TITULO,
                bgcolor=theme.COR_CARTAO,
                selected_color=theme.COR_INDICADOR_NAVEGACAO,
                on_select=lambda _e, v=valor: self.app.page.run_task(self._escolher_status, v),
            )
            for valor, rotulo in opcoes
        ]

    async def _escolher_status(self, valor: str | None) -> None:
        self.filtro_status = valor
        self._montar_chips()
        self.chips.update()
        await self._recarregar()

    async def _ao_escolher_filial(self, e) -> None:
        valor = e.control.value
        self.filtro_filial = None if valor in (None, TODAS_AS_FILIAIS) else int(valor)
        await self._recarregar()

    async def _buscar(self, _e=None) -> None:
        await self._recarregar()

    # --- Carga ------------------------------------------------------------------------

    async def carregar(self) -> None:
        if self.app.sessao.is_admin:
            resultado = await self.app.chamar(ordens.listar_filiais, self.app.sessao.ator_id)
            if resultado.ok:
                self.filial.options = [
                    ft.DropdownOption(key=TODAS_AS_FILIAIS, text=textos.HOME_TODAS_AS_FILIAIS),
                    *[
                        ft.DropdownOption(key=str(f.id), text=f"{f.codigo} - {f.nome}")
                        for f in resultado.valor
                    ],
                ]
                self.filial.value = str(self.filtro_filial)
                self.filial.visible = True
                self.conteudo.update()
        await self._recarregar()

    async def _recarregar(self, _e=None) -> None:
        self.pagina = 1
        self.itens = []
        await self._buscar_pagina()

    async def _carregar_mais(self, _e=None) -> None:
        self.pagina += 1
        await self._buscar_pagina()

    async def _buscar_pagina(self) -> None:
        self.rodape.controls = [basicos.carregando()]
        if self.pagina == 1:
            self.lista.controls = []
        self.conteudo.update()
        resultado = await self.app.chamar(
            ordens.listar_os,
            self.app.sessao.ator_id,
            self.busca.value or None,
            self.filtro_status,
            self.filtro_filial,
            self.pagina,
        )
        self.rodape.controls = []
        if resultado.ok:
            self.itens.extend(resultado.valor.itens)
            self.lista.controls = [self._cartao(item) for item in self.itens]
            if not self.itens:
                self.rodape.controls = [basicos.mensagem_central(textos.HOME_VAZIA)]
            elif resultado.valor.tem_mais:
                self.rodape.controls = [
                    basicos.botao_secundario(
                        textos.HOME_CARREGAR_MAIS, ft.Icons.EXPAND_MORE, self._carregar_mais
                    )
                ]
        try:
            self.conteudo.update()
        except RuntimeError:
            pass  # a tela já foi trocada (por exemplo, a sessão expirou)

    # --- Cartão de uma OS -------------------------------------------------------------

    def _cartao(self, item) -> ft.Control:
        detalhes = [
            formatacao.formatar_brl(item.valor_previsto_centavos),
            formatacao.formatar_data(item.criado_em),
        ]
        if self.app.sessao.is_admin:
            detalhes.append(item.filial_codigo)
        return basicos.cartao(
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        item.numero,
                                        color=theme.COR_SUBTITULO,
                                        size=theme.FONTE_SUBTITULO,
                                    ),
                                    basicos.selo_status(item.status),
                                ],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                            ),
                            ft.Text(
                                item.titulo,
                                color=theme.COR_TITULO,
                                size=theme.FONTE_CORPO,
                                weight=ft.FontWeight.BOLD,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(
                                "  ·  ".join(detalhes),
                                color=theme.COR_SUBTITULO,
                                size=theme.FONTE_SUBTITULO,
                            ),
                        ],
                        spacing=6,
                        expand=True,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=theme.COR_SUBTITULO),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=theme.ESPACO_P,
            ),
            on_click=lambda _e, i=item.id: self.app.page.run_task(self.app.ir, rotas.rota_os(i)),
        )
