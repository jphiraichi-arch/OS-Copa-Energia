"""Home: lista de ordens de serviço com busca e filtros.

Nenhuma regra de filial ou permissão aqui: os filtros vão para o serviço e a tela
mostra o que ele devolver.
"""

from __future__ import annotations

import flet as ft

from osapp import formatacao
from osapp.services import especialidades, ordens, status
from osapp.ui import fase_custo, rotas, rotulos, textos, theme
from osapp.ui.components import basicos
from osapp.ui.components.chips import GrupoChips
from osapp.ui.components.escopo_busca import SeletorEscopo
from osapp.ui.views.base import Tela

TODAS_AS_FILIAIS = "todas"
SOLICITACOES_ABERTAS = "solicitacoes_abertas"  # filtro rápido (manutenção e administrador)
ROTULO_SOLICITACOES_ABERTAS = "Abertas pela operação"  # prompt 41 (era "Solicitações abertas")
ESCOPO_PADRAO = ordens.ESCOPO_TUDO  # decisão de 21/11/2026


class Home(Tela):
    banner = (ft.Icons.ASSIGNMENT, textos.HOME_TITULO)

    def __init__(self, app, **_params) -> None:
        self.app = app
        self.filtro_status: str | None = None
        # Para administrador, o filtro começa na própria filial (ou na última escolhida
        # nesta sessão); os demais não escolhem. A faixa usa o mesmo filtro.
        self.filtro_filial: int | None = app.filtro_filial if app.sessao.e_admin else None
        self.pagina = 1
        self.itens: list = []

        # Na Home a busca começa em 'Tudo'; o relatório começa em 'Itens'.
        self.escopo = (
            None if app.sessao.e_usuario else SeletorEscopo(app, self._buscar, ESCOPO_PADRAO)
        )
        self.busca = basicos.campo_texto(
            textos.HOME_BUSCA,
            hint_text=textos.HOME_BUSCA_DICA_USUARIO
            if app.sessao.e_usuario
            else textos.HOME_BUSCA_DICA,
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
        opcoes = [(None, textos.HOME_TODAS), *status.ROTULOS.items()]
        if not app.sessao.e_usuario:
            opcoes.insert(1, (SOLICITACOES_ABERTAS, ROTULO_SOLICITACOES_ABERTAS))
        self.chips = GrupoChips(
            opcoes,
            None,
            opcional=False,
            ao_mudar=lambda: app.page.run_task(self._escolher_status),
        )
        # Prompt 37: filtro por especialidade (manutenção e administrador).
        self.filtro_especialidade: int | None = None
        self.especialidades = GrupoChips(
            [],
            None,
            opcional=True,
            ao_mudar=lambda: app.page.run_task(self._escolher_especialidade),
        )
        self.especialidades.controle.visible = False
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
            on_click=self._atualizar_tudo,
        )
        self.lista = basicos.coluna([], espaco=theme.ESPACO_M)
        self.rodape = basicos.coluna([])
        self.conteudo = basicos.coluna(
            [
                self.busca,
                *([self.escopo.controle] if self.escopo else []),
                self.chips.controle,
                self.especialidades.controle,
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

    async def _escolher_status(self) -> None:
        self.filtro_status = self.chips.valor
        await self._recarregar()

    async def _escolher_especialidade(self) -> None:
        self.filtro_especialidade = self.especialidades.valor
        await self._recarregar()

    async def _ao_escolher_filial(self, e) -> None:
        valor = e.control.value
        self.filtro_filial = None if valor in (None, TODAS_AS_FILIAIS) else int(valor)
        self.app.filtro_filial = self.filtro_filial
        await self.app.atualizar_contadores()
        await self._recarregar()

    async def _buscar(self, _e=None) -> None:
        await self._recarregar()

    # --- Carga ------------------------------------------------------------------------

    async def carregar(self) -> None:
        if not self.app.sessao.e_usuario:
            lista = await self.app.chamar(especialidades.listar, self.app.sessao.ator_id)
            if lista.ok and lista.valor:
                self.especialidades.opcoes = [(e.id, e.nome) for e in lista.valor]
                self.especialidades.definir(None)
                self.especialidades.controle.visible = True
        if self.app.sessao.e_admin:
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

    async def _atualizar_tudo(self, _e=None) -> None:
        """'Atualizar': a lista e os números da faixa e do selo."""
        await self.app.atualizar_contadores()
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
        rapido = self.filtro_status == SOLICITACOES_ABERTAS
        resultado = await self.app.chamar(
            ordens.listar_os,
            self.app.sessao.ator_id,
            self.busca.value or None,
            status.ABERTA if rapido else self.filtro_status,
            self.filtro_filial,
            self.pagina,
            ordens.ORIGEM_SOLICITACAO if rapido else None,
            self.escopo.valor if self.escopo else ESCOPO_PADRAO,
            None if self.app.sessao.e_usuario else self.filtro_especialidade,
        )
        self.rodape.controls = []
        if resultado.ok:
            self.itens.extend(resultado.valor.itens)
            if rapido:  # Emergencial primeiro, depois a mais antiga
                self.itens = rotulos.ordenar_solicitacoes_abertas(self.itens)
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
        if isinstance(item, ordens.ResumoSolicitante):
            selos = [basicos.selo_nivel(item.urgencia, "Urgência: ")]
            detalhes = [item.solicitante, f"aberta em {formatacao.formatar_data(item.aberta_em)}"]
        else:
            selos = [basicos.selo_origem(item.origem)]
            if item.urgencia:
                selos.append(basicos.selo_nivel(item.urgencia, "Urgência: "))
            if item.prioridade:
                selos.append(basicos.selo_nivel(item.prioridade, "Prioridade: "))
            if item.sla is not None:  # prompt 38 (só manutenção e administrador)
                selos.append(basicos.selo_sla(item.sla))
            detalhes = [
                item.solicitante,
                fase_custo.texto_da_lista(
                    item.tem_itens_previstos,
                    item.sem_gasto_previsto,
                    item.total_previsto_centavos,
                ),
                formatacao.formatar_data(item.aberta_em or item.criado_em),
            ]
            if self.app.sessao.e_admin:
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
                            ft.Row(selos, wrap=True, spacing=6, run_spacing=6),
                            ft.Text(
                                "  ·  ".join(d for d in detalhes if d),
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
