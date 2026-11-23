"""Relatório de tempos de atendimento por mês (/relatorios; prompt 25).

A tela mostra o que o serviço devolver; quem pode ver (manutenção na própria filial,
administrador) e todos os cálculos ficam em services/relatorios.py.
"""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import flet as ft

from osapp import formatacao
from osapp.services import ordens, relatorios, relogio
from osapp.services.erros import ErroPermissao
from osapp.ui import historico, rotas, rotulos, textos, theme
from osapp.ui.components import basicos
from osapp.ui.components.chips import GrupoChips
from osapp.ui.components.escopo_busca import SeletorEscopo
from osapp.ui.components.secao import secao
from osapp.ui.views.base import Tela
from osapp.ui.views.relatorios import mes_vizinho

TODAS = "todas"
ESCOPO_PADRAO = ordens.ESCOPO_ITENS  # decisão de 21/11/2026
SEM_VALOR = "-"


def _tempo(segundos: int | None) -> str:
    return SEM_VALOR if segundos is None else formatacao.formatar_tempo(segundos)


def _percentual(valor: float) -> str:
    """O percentual sem o '%' (o '%' é posto por quem chama)."""
    return formatacao.formatar_percentual(valor).removesuffix("%")


SEM_TAXA = "—"


def texto_taxa(taxa) -> str:
    """'85% (34 de 40)'; '—' quando o denominador é 0."""
    if taxa.percentual is None:
        return SEM_TAXA
    return f"{_percentual(taxa.percentual)}% ({taxa.numerador} de {taxa.denominador})"


def linha_resumo_busca(b) -> str:
    """Ex.: '12 de 40 ordens no período (30%) correspondem a "balança"'."""
    proporcao = f" ({_percentual(b.percentual)}%)" if b.percentual is not None else ""
    verbo = "corresponde" if b.correspondentes == 1 else "correspondem"
    return (
        f"{b.correspondentes} de {b.total_periodo} ordens no período{proporcao} "
        f'{verbo} a "{b.termo}"'
    )


def texto_resumo_mensal(resumo, termo: str, periodo: str) -> str:
    """'3 de 5 ordens de outubro de 2026 (60%) correspondem a "balança"'."""
    proporcao = f" ({_percentual(resumo.percentual)}%)" if resumo.percentual is not None else ""
    verbo = "corresponde" if resumo.correspondentes == 1 else "correspondem"
    return (
        f"{resumo.correspondentes} de {resumo.total} ordens {periodo}{proporcao} "
        f'{verbo} a "{termo}"'
    )


def nome_do_mes(ano: int, mes: int) -> str:
    """'Novembro de 2026'."""
    return textos.nome_do_mes(ano, mes).capitalize()


class RelatorioTempos(Tela):
    """Relatório mensal (prompt 25): seletor de mês, mês selecionado e acumulado."""

    banner = (ft.Icons.INSERT_CHART, textos.NAVEGACAO_RELATORIOS)

    def __init__(self, app, **_params) -> None:
        self.app = app
        hoje = relogio.agora().astimezone(ZoneInfo(app.config.tz))
        self.mes_atual = (hoje.year, hoje.month)
        self.ano, self.mes = self.mes_atual
        self.status = set(relatorios.STATUS_DO_RELATORIO)
        self.filial_id: int | None = None  # None: a própria (manutenção) ou todas (admin)
        self.relatorio = None
        self.pagina = 1
        self.termo = basicos.campo_texto(
            textos.TEMPOS_BUSCA,
            hint_text=textos.TEMPOS_BUSCA_DICA,
            on_submit=self._aplicar,
        )
        self.escopo = SeletorEscopo(app, self._aplicar, ESCOPO_PADRAO)
        self.chips = GrupoChips(
            [(v, rotulos.status(v)) for v in relatorios.STATUS_DO_RELATORIO],
            self.status,
            multipla=True,
            minimo=1,  # pelo menos um status fica marcado
            ao_mudar=self._ao_mudar_status,
        )
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
        self.rotulo_mes = ft.Text(
            nome_do_mes(self.ano, self.mes),
            color=theme.COR_TITULO,
            size=theme.FONTE_TITULO,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
            expand=True,
        )
        self.anterior = self._seta(ft.Icons.CHEVRON_LEFT, textos.REL_MES_ANTERIOR, -1)
        self.seguinte = self._seta(ft.Icons.CHEVRON_RIGHT, textos.REL_PROXIMO_MES, 1)
        self.corpo = basicos.coluna([basicos.carregando()])
        self._atualizar_setas()
        self.conteudo = basicos.coluna(
            [
                basicos.titulo(textos.TEMPOS_TITULO, theme.FONTE_SAUDACAO),
                basicos.subtitulo(textos.MENSAL_NOTA_STATUS),
                basicos.cartao(
                    ft.Row(
                        [self.anterior, self.rotulo_mes, self.seguinte],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    )
                ),
                basicos.cartao(
                    basicos.coluna(
                        [
                            self.termo,
                            self.escopo.controle,
                            self.chips.controle,
                            ft.Row([self.filial]),
                            basicos.botao_secundario(
                                textos.TEMPOS_APLICAR, ft.Icons.FILTER_ALT_OUTLINED, self._aplicar
                            ),
                        ],
                        espaco=theme.ESPACO_P + 4,
                    )
                ),
                self.corpo,
            ]
        )

    # --- Mês ------------------------------------------------------------------------

    def _seta(self, icone, dica: str, passo: int) -> ft.IconButton:
        return ft.IconButton(
            icon=icone,
            icon_color=theme.COR_PRIMARIO,
            tooltip=dica,
            width=theme.ALVO_TOQUE_MIN,
            height=theme.ALVO_TOQUE_MIN,
            on_click=lambda _e: self.app.page.run_task(self._mudar_mes, passo),
        )

    def _atualizar_setas(self) -> None:
        # Meses futuros não podem ser escolhidos (o serviço também recusa).
        self.seguinte.disabled = (self.ano, self.mes) >= self.mes_atual
        self.seguinte.opacity = 0.3 if self.seguinte.disabled else 1

    async def _mudar_mes(self, passo: int) -> None:
        ano, mes = mes_vizinho(self.ano, self.mes, passo)
        if (ano, mes) > self.mes_atual:
            return
        self.ano, self.mes, self.pagina = ano, mes, 1
        self.rotulo_mes.value = nome_do_mes(ano, mes)
        self._atualizar_setas()
        await self._buscar()

    # --- Filtros ----------------------------------------------------------------------

    def _ao_mudar_status(self) -> None:
        self.status = set(self.chips.valor)

    async def _ao_escolher_filial(self, e) -> None:
        valor = e.control.value
        self.filial_id = None if valor in (None, TODAS) else int(valor)

    async def _aplicar(self, _e=None) -> None:
        self.pagina = 1
        await self._buscar()

    async def _ir_para_pagina(self, pagina: int) -> None:
        self.pagina = pagina
        await self._buscar()

    # --- Carga ------------------------------------------------------------------------

    async def carregar(self) -> None:
        if self.app.sessao.e_admin:
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
            relatorios.relatorio_mensal,
            self.app.sessao.ator_id,
            self.ano,
            self.mes,
            (self.termo.value or "").strip() or None,
            self.escopo.valor,
            tuple(self.status),
            self.filial_id,
            self.pagina,
            erros_tratados=(ErroPermissao,),
        )
        if resultado.ok:
            self.relatorio = resultado.valor
            self.corpo.controls = self._montar(resultado.valor)
        else:
            # Recusa do serviço (papel usuario abrindo a rota digitada) ou erro já avisado.
            self.corpo.controls = [basicos.mensagem_central(self.app.MENSAGEM_GENERICA)]
        self._atualizar()

    def _atualizar(self) -> None:
        try:
            self.conteudo.update()
        except RuntimeError:
            pass  # a tela já foi trocada

    # --- Montagem ---------------------------------------------------------------------

    def _montar(self, r) -> list[ft.Control]:
        fim_do_mes = (r.mes_selecionado.fim - timedelta(seconds=1)).astimezone(
            ZoneInfo(self.app.config.tz)
        )
        mes_txt = textos.nome_do_mes(r.ano, r.mes)
        partes: list[ft.Control] = [
            basicos.subtitulo(r.filial_rotulo),
            self._bloco(1, textos.MENSAL_MES, r.mes_selecionado, r.termo, f"de {mes_txt}"),
            self._bloco(
                2,
                f"{textos.MENSAL_ACUMULADO} {fim_do_mes:%d/%m/%Y}",
                r.acumulado,
                r.termo,
                f"até {fim_do_mes:%d/%m/%Y}",
            ),
        ]
        if r.ordens:
            partes.append(self._lista_busca(r))
        elif r.termo:
            partes.append(basicos.cartao(basicos.mensagem_central(textos.TEMPOS_BUSCA_VAZIA)))
        if r.backlog is not None:
            partes.append(_backlog(r.backlog))
        partes.append(
            basicos.botao_secundario(
                textos.TEMPOS_MENSAL, ft.Icons.CALENDAR_MONTH, self._abrir_mensal
            )
        )
        return partes

    def _bloco(self, numero: int, titulo: str, b, termo: str | None, periodo: str) -> ft.Control:
        """Fluxo, taxa, cartões de tempo e custos de um bloco (mês ou acumulado)."""
        f = b.fluxo
        linhas: list[ft.Control] = []
        if b.busca is not None:
            linhas.append(
                ft.Text(
                    texto_resumo_mensal(b.busca, termo, periodo),
                    color=theme.COR_TITULO,
                    size=theme.FONTE_CORPO,
                    weight=ft.FontWeight.BOLD,
                )
            )
        linhas += [
            ft.ResponsiveRow(
                [
                    ft.Container(
                        col={"xs": 4},
                        content=basicos.rotulo_valor(rotulo, str(valor), uma_linha=True),
                    )
                    for rotulo, valor in (
                        (textos.MENSAL_ABERTAS, f.abertas),
                        (textos.MENSAL_CONCLUIDAS, f.concluidas),
                        (textos.MENSAL_CANCELADAS, f.canceladas),
                    )
                ],
                spacing=theme.ESPACO_M,
            ),
            basicos.rotulo_valor(textos.MENSAL_TAXA, texto_taxa(b.taxa), uma_linha=True),
            basicos.subtitulo(textos.MENSAL_TAXA_NOTA),
        ]
        if b.resposta.n or b.solucao.n:
            linhas += [
                ft.ResponsiveRow(
                    [
                        self._cartao_medida(
                            textos.TEMPOS_RESPOSTA, textos.TEMPOS_RESPOSTA_AJUDA, b.resposta
                        ),
                        self._cartao_medida(
                            textos.TEMPOS_SOLUCAO, textos.TEMPOS_SOLUCAO_AJUDA, b.solucao
                        ),
                    ],
                    spacing=theme.ESPACO_M,
                    run_spacing=theme.ESPACO_M,
                ),
                basicos.subtitulo(textos.TEMPOS_NOTA),
                self._por_urgencia(b),
            ]
        else:
            linhas.append(basicos.subtitulo(textos.TEMPOS_VAZIO))
        linhas.append(self._custos_busca(b.custos))
        return secao(numero, ft.Icons.INSERT_CHART_OUTLINED, titulo, linhas)

    async def _abrir_mensal(self, _e=None) -> None:
        await self.app.ir(rotas.RELATORIO_MENSAL)

    def _cartao_medida(self, titulo: str, ajuda: str, m) -> ft.Control:
        return ft.Container(
            col={"xs": 12, "sm": 6},
            content=basicos.cartao(
                basicos.coluna(
                    [
                        basicos.titulo(titulo, theme.FONTE_CORPO + 2),
                        basicos.subtitulo(ajuda),
                        ft.Row(
                            [
                                basicos.rotulo_valor(
                                    textos.TEMPOS_MEDIA, _tempo(m.media_segundos), uma_linha=True
                                ),
                                basicos.rotulo_valor(
                                    textos.TEMPOS_MEDIANA,
                                    _tempo(m.mediana_segundos),
                                    uma_linha=True,
                                ),
                                basicos.rotulo_valor("n", str(m.n), uma_linha=True),
                            ],
                            spacing=theme.ESPACO_G,
                            wrap=True,
                        ),
                    ],
                    espaco=theme.ESPACO_P,
                )
            ),
        )

    def _por_urgencia(self, r) -> ft.Control:
        """Tabela em telas largas; um cartão por urgência no celular."""
        if self.app._e_largo():
            cabecalho = (
                "Urgência",
                "Resposta (média)",
                "Resposta (mediana)",
                "Solução (média)",
                "Solução (mediana)",
                "n (resposta / solução)",
            )
            linhas = [_linha_tabela(cabecalho, True)]
            for u in r.por_urgencia:
                linhas.append(ft.Divider(height=1, thickness=1, color=theme.COR_CONTORNO))
                linhas.append(
                    _linha_tabela(
                        (
                            rotulos.nivel(u.urgencia),
                            _tempo(u.resposta.media_segundos),
                            _tempo(u.resposta.mediana_segundos),
                            _tempo(u.solucao.media_segundos),
                            _tempo(u.solucao.mediana_segundos),
                            f"{u.resposta.n} / {u.solucao.n}",
                        ),
                        False,
                    )
                )
            corpo = linhas
        else:
            corpo = [
                ft.Container(
                    bgcolor=theme.COR_FUNDO_PAGINA,
                    border_radius=theme.RAIO_BOTAO,
                    padding=theme.ESPACO_P + 4,
                    content=basicos.coluna(
                        [
                            ft.Row([basicos.selo_nivel(u.urgencia)]),
                            basicos.rotulo_valor(
                                f"{textos.TEMPOS_RESPOSTA} (n = {u.resposta.n})",
                                f"média {_tempo(u.resposta.media_segundos)} · "
                                f"mediana {_tempo(u.resposta.mediana_segundos)}",
                            ),
                            basicos.rotulo_valor(
                                f"{textos.TEMPOS_SOLUCAO} (n = {u.solucao.n})",
                                f"média {_tempo(u.solucao.media_segundos)} · "
                                f"mediana {_tempo(u.solucao.mediana_segundos)}",
                            ),
                        ],
                        espaco=theme.ESPACO_P,
                    ),
                )
                for u in r.por_urgencia
            ]
        return basicos.cartao(
            basicos.coluna(
                [basicos.titulo(textos.TEMPOS_POR_URGENCIA), *corpo], espaco=theme.ESPACO_P
            )
        )

    # --- Busca (prompt 22) ------------------------------------------------------------

    @staticmethod
    def _custos_busca(c) -> ft.Control:
        return basicos.cartao(
            basicos.coluna(
                [
                    basicos.titulo(textos.TEMPOS_CUSTOS, theme.FONTE_CORPO + 2),
                    basicos.rotulo_valor(
                        textos.TEMPOS_PREVISTO_TODAS,
                        formatacao.formatar_brl(c.previsto_total_centavos),
                        uma_linha=True,
                    ),
                    basicos.subtitulo(textos.TEMPOS_CUSTOS_NOTA.format(n=c.concluidas)),
                    ft.Row(
                        [
                            basicos.rotulo_valor(
                                textos.TEMPOS_PREVISTO,
                                formatacao.formatar_brl(c.previsto_concluidas_centavos),
                                uma_linha=True,
                            ),
                            basicos.rotulo_valor(
                                textos.TEMPOS_REALIZADO,
                                formatacao.formatar_brl(c.realizado_concluidas_centavos),
                                uma_linha=True,
                            ),
                        ],
                        spacing=theme.ESPACO_G,
                        wrap=True,
                    ),
                    basicos.rotulo_valor(
                        textos.TEMPOS_DIFERENCA,
                        historico.texto_diferenca_valor(
                            c.diferenca_centavos, c.diferenca_percentual
                        )
                        if c.concluidas
                        else SEM_VALOR,
                    ),
                ],
                espaco=theme.ESPACO_P,
            )
        )

    def _lista_busca(self, b) -> ft.Control:
        tz = self.app.config.tz
        cartoes: list[ft.Control] = []
        for o in b.ordens:
            valores = f"Previsto {formatacao.formatar_brl(o.previsto_centavos)}"
            if o.realizado_centavos is not None:
                valores += f" · Realizado {formatacao.formatar_brl(o.realizado_centavos)}"

            async def abrir(_e=None, os_id=o.os_id) -> None:
                await self.app.ir(rotas.rota_os(os_id))

            cartoes.append(
                ft.Container(
                    bgcolor=theme.COR_FUNDO_PAGINA,
                    border_radius=theme.RAIO_BOTAO,
                    padding=theme.ESPACO_P + 4,
                    ink=True,
                    on_click=abrir,
                    content=basicos.coluna(
                        [
                            ft.Text(
                                f"{o.numero} · {o.titulo}",
                                color=theme.COR_TITULO,
                                size=theme.FONTE_CORPO,
                                weight=ft.FontWeight.BOLD,
                            ),
                            basicos.subtitulo(
                                f"{rotulos.status(o.status)} · {rotulos.nivel(o.urgencia)} · "
                                f"aberta em {formatacao.formatar_data_hora(o.aberta_em, tz)}"
                            ),
                            basicos.subtitulo(valores),
                        ],
                        espaco=2,
                    ),
                )
            )
        navegar: list[ft.Control] = []
        if b.pagina > 1:
            navegar.append(
                basicos.botao_secundario(
                    textos.TEMPOS_PAGINA_ANTERIOR,
                    ft.Icons.CHEVRON_LEFT,
                    lambda _e: self.app.page.run_task(self._ir_para_pagina, b.pagina - 1),
                )
            )
        if b.pagina < b.total_paginas:
            navegar.append(
                basicos.botao_secundario(
                    textos.TEMPOS_PROXIMA_PAGINA,
                    ft.Icons.CHEVRON_RIGHT,
                    lambda _e: self.app.page.run_task(self._ir_para_pagina, b.pagina + 1),
                )
            )
        return basicos.cartao(
            basicos.coluna(
                [
                    basicos.titulo(textos.TEMPOS_ORDENS, theme.FONTE_CORPO + 2),
                    basicos.subtitulo(f"Página {b.pagina} de {b.total_paginas}"),
                    *cartoes,
                    *navegar,
                ],
                espaco=theme.ESPACO_P,
            )
        )


def _backlog(b) -> ft.Control:
    """Solicitações abertas agora (não depende do mês escolhido)."""
    texto = (
        f"{textos.TEMPOS_MAIS_ANTIGA} {_tempo(b.mais_antiga_segundos)}"
        if b.mais_antiga_segundos is not None
        else SEM_VALOR
    )
    return basicos.cartao(
        basicos.coluna(
            [
                basicos.titulo(textos.TEMPOS_ABERTAS, theme.FONTE_CORPO + 2),
                basicos.subtitulo(textos.TEMPOS_ABERTAS_AGORA),
                *(
                    [basicos.subtitulo(f"{textos.TEMPOS_FILTRADO_POR} {b.filtrado_por}")]
                    if b.filtrado_por
                    else []
                ),
                ft.Row(
                    [
                        basicos.rotulo_valor(
                            textos.TEMPOS_QUANTIDADE, str(b.quantidade), uma_linha=True
                        ),
                        basicos.rotulo_valor("Mais antiga", texto),
                    ],
                    spacing=theme.ESPACO_G,
                    wrap=True,
                ),
            ],
            espaco=theme.ESPACO_P,
        )
    )


def _linha_tabela(celulas: tuple[str, ...], destaque: bool) -> ft.Control:
    peso = ft.FontWeight.BOLD if destaque else ft.FontWeight.NORMAL
    larguras = (3, 3, 3, 3, 3, 2)
    return ft.Row(
        [
            ft.Text(
                texto,
                color=theme.COR_TITULO,
                size=theme.FONTE_SUBTITULO,
                weight=peso,
                expand=largura,
                no_wrap=n > 0,  # valores numa linha só; o rótulo da linha é que quebra
                text_align=ft.TextAlign.LEFT if n == 0 else ft.TextAlign.RIGHT,
            )
            for n, (texto, largura) in enumerate(zip(celulas, larguras, strict=True))
        ],
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
