"""Relatório de tempos de atendimento (/relatorios).

A tela mostra o que o serviço devolver; quem pode ver (manutenção na própria filial,
administrador) e todos os cálculos ficam em services/relatorios.py.
"""

from __future__ import annotations

from datetime import date

import flet as ft

from osapp import formatacao
from osapp.services import ordens, relatorios
from osapp.services.erros import ErroPermissao
from osapp.ui import formularios, rotas, rotulos, textos, theme
from osapp.ui.components import basicos
from osapp.ui.views.base import Tela

TODAS = "todas"
SEM_VALOR = "-"


def _tempo(segundos: int | None) -> str:
    return SEM_VALOR if segundos is None else formatacao.formatar_tempo(segundos)


def _data(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}/{d.year:04d}"


class RelatorioTempos(Tela):
    def __init__(self, app, **_params) -> None:
        self.app = app
        self.status = set(relatorios.STATUS_DO_RELATORIO)
        self.filial_id: int | None = None  # None: a própria (manutenção) ou todas (admin)
        self.relatorio = None
        self.de = basicos.campo_texto(
            textos.TEMPOS_DE,
            hint_text="dd/mm/aaaa",
            keyboard_type=ft.KeyboardType.DATETIME,
            expand=True,
        )
        self.ate = basicos.campo_texto(
            textos.TEMPOS_ATE,
            hint_text="dd/mm/aaaa",
            keyboard_type=ft.KeyboardType.DATETIME,
            expand=True,
        )
        self.chips = ft.Row(wrap=True, spacing=theme.ESPACO_P, run_spacing=theme.ESPACO_P)
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
        self.corpo = basicos.coluna([basicos.carregando()])
        self._montar_chips()
        self.conteudo = basicos.coluna(
            [
                basicos.titulo(textos.TEMPOS_TITULO, theme.FONTE_SAUDACAO),
                basicos.cartao(
                    basicos.coluna(
                        [
                            basicos.subtitulo(textos.TEMPOS_PERIODO),
                            ft.Row([self.de, self.ate], spacing=theme.ESPACO_P),
                            self.chips,
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

    # --- Filtros ----------------------------------------------------------------------

    def _montar_chips(self) -> None:
        self.chips.controls = [
            ft.Chip(
                label=ft.Text(
                    rotulos.status(valor), color=theme.COR_TITULO, size=theme.FONTE_SUBTITULO
                ),
                selected=valor in self.status,
                show_checkmark=True,
                check_color=theme.COR_TITULO,
                bgcolor=theme.COR_CARTAO,
                selected_color=theme.COR_INDICADOR_NAVEGACAO,
                on_select=lambda _e, v=valor: self._alternar_status(v),
            )
            for valor in relatorios.STATUS_DO_RELATORIO
        ]

    def _alternar_status(self, valor: str) -> None:
        if valor in self.status and len(self.status) > 1:  # pelo menos um fica marcado
            self.status.discard(valor)
        else:
            self.status.add(valor)
        self._montar_chips()
        self.chips.update()

    async def _ao_escolher_filial(self, e) -> None:
        valor = e.control.value
        self.filial_id = None if valor in (None, TODAS) else int(valor)

    def _ler_datas(self) -> tuple[date, date] | None:
        erros = False
        datas = []
        for campo in (self.de, self.ate):
            campo.error = None
            try:
                datas.append(formularios.ler_data(campo.value))
            except ValueError as exc:
                campo.error = str(exc)
                erros = True
        return None if erros else (datas[0], datas[1])

    async def _aplicar(self, _e=None) -> None:
        datas = self._ler_datas()
        if datas is None:
            self.conteudo.update()
            return
        await self._buscar(*datas)

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
        await self._buscar(None, None)  # padrão do serviço: os últimos 30 dias

    async def _buscar(self, data_inicio, data_fim) -> None:
        self.corpo.controls = [basicos.carregando()]
        self._atualizar()
        resultado = await self.app.chamar(
            relatorios.relatorio_tempos,
            self.app.sessao.ator_id,
            data_inicio,
            data_fim,
            tuple(self.status),
            self.filial_id,
            erros_tratados=(ErroPermissao,),
        )
        if resultado.ok:
            r = resultado.valor
            self.relatorio = r
            self.de.value, self.ate.value = _data(r.data_inicio), _data(r.data_fim)
            self.corpo.controls = self._montar(r)
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
        partes: list[ft.Control] = [basicos.subtitulo(r.filial_rotulo)]
        if r.total_no_periodo == 0:
            partes.append(basicos.cartao(basicos.mensagem_central(textos.TEMPOS_VAZIO)))
        else:
            partes += [
                ft.ResponsiveRow(
                    [
                        self._cartao_medida(
                            textos.TEMPOS_RESPOSTA, textos.TEMPOS_RESPOSTA_AJUDA, r.resposta
                        ),
                        self._cartao_medida(
                            textos.TEMPOS_SOLUCAO, textos.TEMPOS_SOLUCAO_AJUDA, r.solucao
                        ),
                    ],
                    spacing=theme.ESPACO_M,
                    run_spacing=theme.ESPACO_M,
                ),
                basicos.subtitulo(textos.TEMPOS_NOTA),
                self._por_urgencia(r),
            ]
        partes.append(self._backlog(r.backlog))
        partes.append(
            basicos.botao_secundario(
                textos.TEMPOS_MENSAL, ft.Icons.CALENDAR_MONTH, self._abrir_mensal
            )
        )
        return partes

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
                                basicos.rotulo_valor(textos.TEMPOS_MEDIA, _tempo(m.media_segundos)),
                                basicos.rotulo_valor(
                                    textos.TEMPOS_MEDIANA, _tempo(m.mediana_segundos)
                                ),
                                basicos.rotulo_valor("n", str(m.n)),
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

    @staticmethod
    def _backlog(b) -> ft.Control:
        texto = (
            f"{textos.TEMPOS_MAIS_ANTIGA} {_tempo(b.mais_antiga_segundos)}"
            if b.mais_antiga_segundos is not None
            else SEM_VALOR
        )
        return basicos.cartao(
            basicos.coluna(
                [
                    basicos.titulo(textos.TEMPOS_ABERTAS, theme.FONTE_CORPO + 2),
                    ft.Row(
                        [
                            basicos.rotulo_valor(textos.TEMPOS_QUANTIDADE, str(b.quantidade)),
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
                text_align=ft.TextAlign.LEFT if n == 0 else ft.TextAlign.RIGHT,
            )
            for n, (texto, largura) in enumerate(zip(celulas, larguras, strict=True))
        ],
        vertical_alignment=ft.CrossAxisAlignment.START,
    )
