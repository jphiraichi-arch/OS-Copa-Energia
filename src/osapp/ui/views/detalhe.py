"""Detalhe da OS."""

from __future__ import annotations

import flet as ft

from osapp import formatacao
from osapp.services import ordens, status
from osapp.services.erros import ErroNaoEncontrado
from osapp.ui import historico, rotas, theme
from osapp.ui.components import basicos
from osapp.ui.views.base import Tela


class Detalhe(Tela):
    def __init__(self, app, os_id: int, **_params) -> None:
        self.app = app
        self.os_id = os_id
        self.os = None
        self.conteudo = basicos.coluna([basicos.carregando()])

    async def carregar(self) -> None:
        ator_id = self.app.sessao.ator_id
        resultado = await self.app.chamar(
            ordens.obter_os, ator_id, self.os_id, erros_tratados=(ErroNaoEncontrado,)
        )
        eventos = None
        if resultado.ok:
            eventos = await self.app.chamar(
                ordens.listar_eventos, ator_id, self.os_id, erros_tratados=(ErroNaoEncontrado,)
            )
        if resultado.ok and eventos.ok:
            self.os = resultado.valor
            self.conteudo.controls = self._montar(resultado.valor, eventos.valor)
        elif isinstance(resultado.erro, ErroNaoEncontrado) or (
            eventos is not None and isinstance(eventos.erro, ErroNaoEncontrado)
        ):
            self.conteudo.controls = self._nao_encontrada()
        else:
            self.conteudo.controls = [
                basicos.mensagem_central("Não foi possível carregar a OS."),
                basicos.botao_secundario("Voltar para a lista", ft.Icons.LIST, self._para_lista),
            ]
        try:
            self.conteudo.update()
        except RuntimeError:
            pass  # a tela já foi trocada (por exemplo, a sessão expirou)

    async def _para_lista(self, _e=None) -> None:
        await self.app.ir(rotas.HOME)

    def _nao_encontrada(self) -> list[ft.Control]:
        return [
            basicos.mensagem_central("OS não encontrada."),
            basicos.botao_secundario("Voltar para a lista", ft.Icons.LIST, self._para_lista),
        ]

    # --- Montagem ---------------------------------------------------------------------

    def _montar(self, d, eventos) -> list[ft.Control]:
        topo = basicos.cartao(
            basicos.coluna(
                [
                    ft.Row(
                        [
                            ft.Text(
                                d.numero,
                                color=theme.COR_SUBTITULO,
                                size=theme.FONTE_CORPO,
                                weight=ft.FontWeight.BOLD,
                            ),
                            basicos.selo_status(d.status),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    basicos.titulo(d.titulo, theme.FONTE_SAUDACAO),
                    basicos.rotulo_valor("Filial", f"{d.filial_codigo} - {d.filial_nome}"),
                    basicos.rotulo_valor(
                        "Criada por",
                        f"{d.criado_por_nome}, em {formatacao.formatar_data_hora(d.criado_em)}",
                    ),
                ],
                espaco=theme.ESPACO_P + 4,
            )
        )
        previsto = self._secao(
            "Previsto",
            [
                basicos.rotulo_valor("Descrição", d.descricao),
                basicos.rotulo_valor(
                    "Valor previsto", formatacao.formatar_brl(d.valor_previsto_centavos)
                ),
                basicos.rotulo_valor(
                    "Tempo previsto", formatacao.formatar_duracao(d.tempo_previsto_minutos)
                ),
            ],
        )
        cartoes = [topo, *self._acoes(d), previsto, self._realizado(d)]
        if d.diferenca_valor_centavos is not None and d.diferenca_tempo_minutos is not None:
            cartoes.append(
                self._secao(
                    "Diferença",
                    [
                        basicos.rotulo_valor(
                            "Valor (realizado - previsto)",
                            historico.texto_diferenca_valor(
                                d.diferenca_valor_centavos, d.diferenca_valor_percentual
                            ),
                        ),
                        basicos.rotulo_valor(
                            "Tempo (realizado - previsto)",
                            historico.texto_diferenca_tempo(d.diferenca_tempo_minutos),
                        ),
                    ],
                )
            )
        cartoes.append(self._historico(eventos))
        return cartoes

    def _acoes(self, d) -> list[ft.Control]:
        """Botões de ação, mostrados conforme ``acoes`` (calculado pelo serviço).

        Esconder um botão é só conveniência: quem autoriza é o serviço.
        """
        botoes: list[ft.Control] = []
        if d.acoes.pode_editar:
            botoes.append(basicos.botao_secundario("Alterar", ft.Icons.EDIT, self._alterar))
        return botoes

    async def _alterar(self, _e=None) -> None:
        await self.app.ir(rotas.rota_editar(self.os_id))

    def _secao(self, nome: str, linhas: list[ft.Control]) -> ft.Control:
        return basicos.cartao(
            basicos.coluna([basicos.titulo(nome), *linhas], espaco=theme.ESPACO_P + 4)
        )

    def _realizado(self, d) -> ft.Control:
        if not status.encerrado(d.status) or d.valor_realizado_centavos is None:
            return self._secao("Realizado", [basicos.subtitulo("Preenchido na conclusão.")])
        return self._secao(
            "Realizado",
            [
                basicos.rotulo_valor(
                    "Valor realizado", formatacao.formatar_brl(d.valor_realizado_centavos)
                ),
                basicos.rotulo_valor("Início", formatacao.formatar_data_hora(d.inicio_realizado)),
                basicos.rotulo_valor("Fim", formatacao.formatar_data_hora(d.fim_realizado)),
                basicos.rotulo_valor(
                    "Tempo realizado", formatacao.formatar_duracao(d.tempo_realizado_minutos)
                ),
                basicos.rotulo_valor("Descrição do que foi feito", d.descricao_realizado),
                basicos.rotulo_valor(
                    "Concluída por",
                    f"{d.concluido_por_nome}, em {formatacao.formatar_data_hora(d.concluido_em)}",
                ),
            ],
        )

    def _historico(self, eventos) -> ft.Control:
        linhas: list[ft.Control] = []
        for evento in reversed(eventos):  # do mais novo para o mais antigo
            if linhas:
                linhas.append(ft.Divider(height=1, thickness=1, color=theme.COR_CONTORNO))
            linhas.append(
                ft.Column(
                    [
                        ft.Text(
                            f"{formatacao.formatar_data_hora(evento.data_hora)}  ·  "
                            f"{evento.nome_usuario}",
                            color=theme.COR_SUBTITULO,
                            size=theme.FONTE_PEQUENA,
                        ),
                        ft.Text(
                            historico.frase(evento),
                            color=theme.COR_TITULO,
                            size=theme.FONTE_SUBTITULO,
                        ),
                    ],
                    spacing=2,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                )
            )
        return self._secao("Histórico", linhas)
