"""Tela Relatórios (/relatorios).

Mostra o que o serviço devolver: o relatório completo só chega preenchido para quem pode
vê-lo (gerente na própria filial, administrador). A tela não decide permissão.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

import flet as ft

from osapp import formatacao
from osapp.services import ordens, relatorios, relogio
from osapp.ui import historico, rotas, textos, theme
from osapp.ui.components import basicos
from osapp.ui.views.base import Tela

TODAS = "todas"
LARGURA_INDICADOR = 150


def mes_vizinho(ano: int, mes: int, passo: int) -> tuple[int, int]:
    """Mês anterior (passo -1) ou seguinte (passo +1)."""
    indice = ano * 12 + (mes - 1) + passo
    return indice // 12, indice % 12 + 1


class Relatorios(Tela):
    def __init__(self, app, **_params) -> None:
        self.app = app
        hoje = relogio.agora().astimezone(ZoneInfo(app.config.tz))
        self.mes_atual = (hoje.year, hoje.month)
        self.ano, self.mes = self.mes_atual
        self.filial_id: int | None = None  # None: a própria filial (ou todas, para admin)

        self.rotulo_mes = ft.Text(
            "",
            color=theme.COR_TITULO,
            size=theme.FONTE_CORPO,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
            expand=True,
        )
        self.anterior = self._botao_mes(ft.Icons.CHEVRON_LEFT, textos.REL_MES_ANTERIOR, -1)
        self.proximo = self._botao_mes(ft.Icons.CHEVRON_RIGHT, textos.REL_PROXIMO_MES, 1)
        self.filial = ft.Dropdown(
            label=textos.REL_FILIAL,
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
        self.corpo = basicos.coluna([])
        self.conteudo = basicos.coluna(
            [
                basicos.titulo(textos.REL_TITULO, theme.FONTE_SAUDACAO),
                basicos.cartao(
                    ft.Row(
                        [self.anterior, self.rotulo_mes, self.proximo],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    )
                ),
                ft.Row([self.filial]),
                self.corpo,
            ]
        )
        self._atualizar_periodo()

    # --- Período e filial -------------------------------------------------------------

    def _botao_mes(self, icone, dica: str, passo: int) -> ft.IconButton:
        async def ao_clicar(_e=None) -> None:
            self.ano, self.mes = mes_vizinho(self.ano, self.mes, passo)
            self._atualizar_periodo()
            await self._buscar()

        return ft.IconButton(
            icon=icone,
            icon_color=theme.COR_BOTAO_PRIMARIO,
            tooltip=dica,
            width=theme.ALVO_TOQUE_MIN,
            height=theme.ALVO_TOQUE_MIN,
            on_click=ao_clicar,
        )

    def _atualizar_periodo(self) -> None:
        self.rotulo_mes.value = textos.nome_do_mes(self.ano, self.mes)
        # Meses futuros não têm movimento; o botão só evita uma consulta inútil.
        self.proximo.disabled = (self.ano, self.mes) >= self.mes_atual

    async def _ao_escolher_filial(self, e) -> None:
        valor = e.control.value
        self.filial_id = None if valor in (None, TODAS) else int(valor)
        await self._buscar()

    # --- Carga ------------------------------------------------------------------------

    async def carregar(self) -> None:
        if self.app.sessao.is_admin:
            resultado = await self.app.chamar(ordens.listar_filiais, self.app.sessao.ator_id)
            if resultado.ok:
                self.filial.options = [
                    ft.DropdownOption(key=TODAS, text=textos.REL_TODAS_AS_FILIAIS),
                    *[
                        ft.DropdownOption(key=str(f.id), text=f"{f.codigo} - {f.nome}")
                        for f in resultado.valor
                    ],
                ]
                self.filial.value = TODAS
                self.filial.visible = True
        await self._buscar()

    async def _buscar(self) -> None:
        self.corpo.controls = [basicos.carregando()]
        self._atualizar()
        resultado = await self.app.chamar(
            relatorios.gerar_relatorio,
            self.app.sessao.ator_id,
            self.ano,
            self.mes,
            self.filial_id,
        )
        if resultado.ok:
            self.corpo.controls = self._montar(resultado.valor)
        else:
            self.corpo.controls = [basicos.mensagem_central(textos.REL_ERRO)]
        self._atualizar()

    def _atualizar(self) -> None:
        try:
            self.conteudo.update()
        except RuntimeError:
            pass  # a tela já foi trocada

    # --- Montagem ---------------------------------------------------------------------

    def _indicador(self, rotulo: str, valor: str) -> ft.Control:
        return ft.Container(
            width=LARGURA_INDICADOR,
            content=ft.Column(
                [
                    ft.Text(rotulo, color=theme.COR_SUBTITULO, size=theme.FONTE_PEQUENA),
                    ft.Text(
                        valor,
                        color=theme.COR_TITULO,
                        size=theme.FONTE_TITULO,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
                spacing=2,
            ),
        )

    def _grade(self, itens: list[ft.Control]) -> ft.Row:
        return ft.Row(itens, wrap=True, spacing=theme.ESPACO_P, run_spacing=theme.ESPACO_M)

    def _secao(self, nome: str, icone, linhas: list[ft.Control]) -> ft.Control:
        return basicos.cartao(
            basicos.coluna(
                [
                    ft.Row(
                        [
                            ft.Icon(icone, color=theme.COR_BOTAO_PRIMARIO),
                            # expand: o título quebra em linhas em vez de passar da borda.
                            ft.Container(basicos.titulo(nome), expand=True),
                        ],
                        spacing=theme.ESPACO_P,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                    ),
                    *linhas,
                ],
                espaco=theme.ESPACO_P + 4,
            )
        )

    def _montar(self, rel) -> list[ft.Control]:
        b = rel.basico
        tempo_medio = (
            formatacao.formatar_duracao(b.tempo_medio_execucao_minutos)
            if b.tempo_medio_execucao_minutos is not None
            else "-"
        )
        cartoes = [
            basicos.subtitulo(rel.filial_rotulo),
            self._secao(
                textos.REL_SITUACAO,
                ft.Icons.ASSIGNMENT_OUTLINED,
                [self._grade([self._indicador(c.rotulo, str(c.total)) for c in b.por_status])],
            ),
            self._secao(
                textos.REL_MOVIMENTO,
                ft.Icons.INSERT_CHART_OUTLINED,
                [
                    self._grade(
                        [
                            self._indicador(textos.REL_CRIADAS, str(b.criadas_no_mes)),
                            self._indicador(textos.REL_CONCLUIDAS, str(b.concluidas_no_mes)),
                            self._indicador(textos.REL_TEMPO_MEDIO, tempo_medio),
                        ]
                    )
                ],
            ),
        ]
        if rel.completo is None:
            cartoes.append(
                self._secao(
                    textos.REL_CUSTOS,
                    ft.Icons.LOCK_OUTLINE,
                    [basicos.subtitulo(textos.REL_RESTRITO)],
                )
            )
        else:
            cartoes += self._completo(rel.completo, b.concluidas_no_mes)
        return cartoes

    def _completo(self, c, concluidas: int) -> list[ft.Control]:
        if concluidas == 0:
            return [
                self._secao(
                    textos.REL_CUSTOS,
                    ft.Icons.PAYMENTS_OUTLINED,
                    [basicos.subtitulo(textos.REL_NENHUMA_CONCLUIDA)],
                )
            ]
        brl = formatacao.formatar_brl
        duracao = formatacao.formatar_duracao
        cartoes = [
            self._secao(
                textos.REL_CUSTOS,
                ft.Icons.PAYMENTS_OUTLINED,
                [
                    basicos.subtitulo(textos.REL_CUSTOS_NOTA),
                    self._grade(
                        [
                            self._indicador(textos.REL_GASTO, brl(c.valor_realizado_centavos)),
                            self._indicador(textos.REL_PREVISTO, brl(c.valor_previsto_centavos)),
                            self._indicador(textos.REL_ACIMA, str(c.acima_do_previsto)),
                        ]
                    ),
                    basicos.rotulo_valor(
                        textos.REL_DIFERENCA_VALOR,
                        historico.texto_diferenca_valor(
                            c.diferenca_valor_centavos, c.diferenca_valor_percentual
                        ),
                    ),
                    self._grade(
                        [
                            self._indicador(
                                textos.REL_TEMPO_REALIZADO, duracao(c.tempo_realizado_minutos)
                            ),
                            self._indicador(
                                textos.REL_TEMPO_PREVISTO, duracao(c.tempo_previsto_minutos)
                            ),
                        ]
                    ),
                    basicos.rotulo_valor(
                        textos.REL_DIFERENCA_TEMPO,
                        historico.texto_diferenca_tempo(c.diferenca_tempo_minutos),
                    ),
                ],
            )
        ]
        if c.maiores_desvios:
            cartoes.append(
                self._secao(
                    textos.REL_DESVIOS,
                    ft.Icons.SUMMARIZE_OUTLINED,
                    [self._linha_desvio(d) for d in c.maiores_desvios],
                )
            )
        if c.por_executor:
            cartoes.append(
                self._secao(
                    textos.REL_EXECUTORES,
                    ft.Icons.GROUPS_OUTLINED,
                    [
                        basicos.rotulo_valor(
                            e.nome,
                            f"{e.concluidas} concluída(s)  ·  {brl(e.valor_realizado_centavos)}"
                            f"  ·  {duracao(e.tempo_realizado_minutos)}",
                        )
                        for e in c.por_executor
                    ],
                )
            )
        if c.por_filial:
            cartoes.append(
                self._secao(
                    textos.REL_FILIAIS,
                    ft.Icons.INSERT_CHART_OUTLINED,
                    [
                        basicos.rotulo_valor(
                            f.filial_codigo,
                            f"{f.concluidas} concluída(s)  ·  {brl(f.valor_realizado_centavos)}",
                        )
                        for f in c.por_filial
                    ],
                )
            )
        return cartoes

    def _linha_desvio(self, d) -> ft.Control:
        def brl(centavos: int) -> str:  # espaço inseparável: "R$ 90,00" não quebra ao meio
            return formatacao.formatar_brl(centavos).replace(" ", "\u00a0")

        return ft.Container(
            ink=True,
            border_radius=theme.RAIO_BOTAO,
            padding=ft.Padding.symmetric(vertical=4),
            on_click=lambda _e, i=d.os_id: self.app.page.run_task(self.app.ir, rotas.rota_os(i)),
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                f"{d.numero}  ·  {d.titulo}",
                                color=theme.COR_TITULO,
                                size=theme.FONTE_SUBTITULO,
                                weight=ft.FontWeight.BOLD,
                                max_lines=2,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(
                                f"{brl(d.valor_previsto_centavos)} previsto  ·  "
                                f"{brl(d.valor_realizado_centavos)} realizado  ·  "
                                f"+{brl(d.diferenca_centavos)}",
                                color=theme.COR_SUBTITULO,
                                size=theme.FONTE_PEQUENA,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=theme.COR_SUBTITULO),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
