"""Detalhe da Ordem de Serviço."""

from __future__ import annotations

import flet as ft

from osapp import formatacao
from osapp.services import custos, ordens, status
from osapp.services.erros import ErroConflito, ErroNaoEncontrado, ErroPermissao
from osapp.ui import historico, rotas, rotulos, theme
from osapp.ui.components import basicos
from osapp.ui.views.base import Tela

MENSAGEM_CONFLITO = (
    "Esta Ordem de Serviço foi alterada por outra pessoa. Atualize e tente novamente."
)


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
        solicitante = resultado.ok and isinstance(resultado.valor, ordens.OsVisaoSolicitante)
        if resultado.ok and not solicitante:  # o papel usuario não tem histórico
            eventos = await self.app.chamar(
                ordens.listar_eventos, ator_id, self.os_id, erros_tratados=(ErroNaoEncontrado,)
            )
        if solicitante:
            self.os = resultado.valor
            self.conteudo.controls = self._montar_solicitante(resultado.valor)
        elif resultado.ok and eventos.ok:
            self.os = resultado.valor
            self.conteudo.controls = self._montar(resultado.valor, eventos.valor)
        elif isinstance(resultado.erro, ErroNaoEncontrado) or (
            eventos is not None and isinstance(eventos.erro, ErroNaoEncontrado)
        ):
            self.conteudo.controls = self._nao_encontrada()
        else:
            self.conteudo.controls = [
                basicos.mensagem_central("Não foi possível carregar a Ordem de Serviço."),
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
            basicos.mensagem_central("Ordem de Serviço não encontrada."),
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
                    ft.Row(
                        [
                            basicos.selo_origem(d.origem),
                            *(
                                [basicos.selo_nivel(d.urgencia, "Urgência: ")]
                                if d.origem == ordens.ORIGEM_SOLICITACAO
                                else []
                            ),
                            basicos.selo_nivel(d.prioridade, "Prioridade: "),
                        ],
                        wrap=True,
                        spacing=6,
                        run_spacing=6,
                    ),
                    basicos.rotulo_valor("Filial", f"{d.filial_codigo} - {d.filial_nome}"),
                    *(
                        [
                            basicos.rotulo_valor(
                                "Urgência (informada pelo solicitante)", rotulos.nivel(d.urgencia)
                            )
                        ]
                        if d.origem == ordens.ORIGEM_SOLICITACAO
                        else []
                    ),
                    basicos.rotulo_valor(
                        "Prioridade (definida pela manutenção)", rotulos.nivel(d.prioridade)
                    ),
                    basicos.rotulo_valor("Tipo de manutenção", d.tipo_nome or "Não definido"),
                    *([basicos.rotulo_valor("Nº SAP", d.numero_sap)] if d.numero_sap else []),
                    basicos.rotulo_valor(
                        "Criada por",
                        f"{d.criado_por_nome}, em {formatacao.formatar_data_hora(d.criado_em)}",
                    ),
                    *self._em_execucao(d),
                ],
                espaco=theme.ESPACO_P + 4,
            )
        )
        previsto = self._secao(
            "Previsto",
            [
                basicos.rotulo_valor("Descrição", d.descricao),
                basicos.rotulo_valor(
                    "Tempo previsto",
                    formatacao.formatar_duracao(d.tempo_previsto_minutos)
                    if d.tempo_previsto_minutos is not None
                    else "Não definido",
                ),
                *(
                    [
                        basicos.rotulo_valor(
                            "Falta para iniciar", ", ".join(d.pendencias_para_iniciar)
                        )
                    ]
                    if d.status == status.ABERTA and d.pendencias_para_iniciar
                    else []
                ),
            ],
        )
        cartoes = [topo, *self._acoes(d)]
        if d.nota_conclusao:
            cartoes.append(_cartao_nota(d.nota_conclusao, "Nota para o solicitante"))
        cartoes += [self._datas(d), previsto, self._realizado(d), self._custos(d)]
        if d.diferenca_tempo_minutos is not None:
            cartoes.append(
                self._secao(
                    "Diferença de tempo",
                    [
                        basicos.rotulo_valor(
                            "Tempo (realizado - previsto)",
                            historico.texto_diferenca_tempo(d.diferenca_tempo_minutos),
                        )
                    ],
                )
            )
        cartoes += [self._itens(d, fase) for fase in custos.FASES if _tem_fase(d, fase)]
        cartoes.append(self._historico(eventos))
        return cartoes

    def _em_execucao(self, d) -> list[ft.Control]:
        """Quem iniciou e quando, enquanto a OS está em execução."""
        if (
            d.status != status.EM_EXECUCAO
            or d.executor_nome is None
            or d.inicio_execucao_em is None
        ):
            return []
        return [
            basicos.rotulo_valor(
                "Em execução por",
                f"{d.executor_nome}, desde {formatacao.formatar_data_hora(d.inicio_execucao_em)}",
            )
        ]

    def _datas(self, d) -> ft.Control:
        """Os quatro instantes de status (linha do tempo)."""
        return self._secao("Datas", _linha_do_tempo(d))

    def _acoes(self, d) -> list[ft.Control]:
        """Botões de ação, mostrados conforme ``acoes`` (calculado pelo serviço).

        Esconder um botão é só conveniência: quem autoriza é o serviço.
        """
        botoes: list[ft.Control] = []
        assumir = (
            d.origem == ordens.ORIGEM_SOLICITACAO
            and d.status == status.ABERTA
            and d.acoes.pode_editar
        )
        if assumir:
            botoes.append(
                basicos.botao_primario("Assumir solicitação", ft.Icons.HANDYMAN, self._assumir)
            )
        if d.acoes.pode_iniciar:
            botoes.append(
                basicos.botao_primario(
                    "Iniciar execução", ft.Icons.PLAY_ARROW, self._perguntar_iniciar
                )
            )
        if d.acoes.pode_concluir:
            botoes.append(
                basicos.botao_primario(
                    "Concluir Ordem de Serviço", ft.Icons.CHECK_CIRCLE_OUTLINE, self._concluir
                )
            )
        if d.acoes.pode_desfazer_inicio:
            botoes.append(
                basicos.botao_secundario("Desfazer início", ft.Icons.UNDO, self._perguntar_desfazer)
            )
        if d.acoes.pode_editar and not assumir:
            botoes.append(basicos.botao_secundario("Alterar", ft.Icons.EDIT, self._alterar))
        if d.acoes.pode_editar_solicitacao:
            botoes.append(
                basicos.botao_secundario(
                    "Editar solicitação", ft.Icons.EDIT_NOTE, self._editar_solicitacao
                )
            )
        if d.acoes.pode_cancelar:
            botoes.append(
                basicos.botao_secundario(
                    "Cancelar", ft.Icons.CANCEL_OUTLINED, self._perguntar_cancelar
                )
            )
        return botoes

    # --- Visão do solicitante (papel usuario) -------------------------------------------

    def _montar_solicitante(self, v) -> list[ft.Control]:
        """Só o modelo reduzido: nada de custos, itens, executor ou histórico."""
        topo = basicos.cartao(
            basicos.coluna(
                [
                    ft.Row(
                        [
                            ft.Text(
                                v.numero,
                                color=theme.COR_SUBTITULO,
                                size=theme.FONTE_CORPO,
                                weight=ft.FontWeight.BOLD,
                            ),
                            basicos.selo_status(v.status),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    basicos.titulo(v.titulo, theme.FONTE_SAUDACAO),
                    ft.Row([basicos.selo_nivel(v.urgencia, "Urgência: ")], wrap=True),
                    basicos.rotulo_valor("Descrição", v.descricao),
                    basicos.rotulo_valor("Solicitante", v.solicitante),
                    basicos.rotulo_valor("Filial", v.filial_codigo),
                ],
                espaco=theme.ESPACO_P + 4,
            )
        )
        cartoes: list[ft.Control] = [topo]
        if v.nota_conclusao:
            cartoes.append(_cartao_nota(v.nota_conclusao, "Nota da manutenção"))
        cartoes.append(self._secao("Andamento", _linha_do_tempo(v)))
        if v.acoes.pode_editar:
            cartoes.append(
                basicos.botao_secundario("Editar", ft.Icons.EDIT, self._editar_solicitacao)
            )
        if v.acoes.pode_cancelar:
            cartoes.append(
                basicos.botao_secundario(
                    "Cancelar solicitação", ft.Icons.CANCEL_OUTLINED, self._perguntar_cancelar
                )
            )
        return cartoes

    async def _assumir(self, _e=None) -> None:
        await self.app.ir(rotas.rota_assumir(self.os_id))

    async def _editar_solicitacao(self, _e=None) -> None:
        await self.app.ir(rotas.rota_editar_solicitacao(self.os_id))

    def _perguntar_cancelar(self, _e=None) -> None:
        self.app.confirmar(
            "Cancelar solicitação?",
            "A Ordem de Serviço será cancelada e não poderá mais ser iniciada nem editada.",
            "Sim, cancelar",
            lambda: self._mudar_status(ordens.cancelar, "Solicitação cancelada."),
            rotulo_cancelar="Voltar",
        )

    async def _alterar(self, _e=None) -> None:
        await self.app.ir(rotas.rota_editar(self.os_id))

    async def _concluir(self, _e=None) -> None:
        await self.app.ir(rotas.rota_concluir(self.os_id))

    def _perguntar_iniciar(self, _e=None) -> None:
        self.app.confirmar(
            "Iniciar execução?",
            "Você passa a ser o executor desta Ordem de Serviço. Só você (ou um "
            "administrador) poderá concluí-la ou desfazer o início.",
            "Iniciar",
            lambda: self._mudar_status(ordens.iniciar_execucao, "Execução iniciada."),
        )

    def _perguntar_desfazer(self, _e=None) -> None:
        self.app.confirmar(
            "Desfazer início?",
            "A Ordem de Serviço volta para o status Aberta e fica sem executor. Outra pessoa "
            "poderá iniciá-la.",
            "Desfazer início",
            lambda: self._mudar_status(ordens.desfazer_inicio, "Início desfeito."),
        )

    async def _mudar_status(self, funcao, mensagem_de_sucesso: str) -> None:
        resultado = await self.app.chamar(
            funcao,
            self.app.sessao.ator_id,
            self.os_id,
            self.os.versao,
            erros_tratados=(ErroConflito, ErroPermissao, ErroNaoEncontrado),
        )
        if resultado.ok:
            self.app.avisar(mensagem_de_sucesso)
        elif isinstance(resultado.erro, ErroConflito):
            self.app.avisar(MENSAGEM_CONFLITO)
        elif isinstance(resultado.erro, ErroPermissao | ErroNaoEncontrado):
            self.app.avisar(self.app.MENSAGEM_GENERICA)
        else:
            return  # sessão encerrada ou erro já avisado
        await self.carregar()  # mostra o estado atual da Ordem de Serviço

    def _secao(self, nome: str, linhas: list[ft.Control]) -> ft.Control:
        return basicos.cartao(
            basicos.coluna([basicos.titulo(nome), *linhas], espaco=theme.ESPACO_P + 4)
        )

    def _realizado(self, d) -> ft.Control:
        if not status.encerrado(d.status) or d.inicio_realizado is None:
            return self._secao("Realizado", [basicos.subtitulo("Preenchido na conclusão.")])
        return self._secao(
            "Realizado",
            [
                basicos.rotulo_valor("Início", formatacao.formatar_data_hora(d.inicio_realizado)),
                basicos.rotulo_valor("Fim", formatacao.formatar_data_hora(d.fim_realizado)),
                basicos.rotulo_valor(
                    "Tempo realizado", formatacao.formatar_duracao(d.tempo_realizado_minutos)
                ),
                basicos.rotulo_valor("Descrição do que foi feito", d.descricao_realizado),
                basicos.rotulo_valor(
                    "Concluída por",
                    f"{d.concluido_por_nome}, em {formatacao.formatar_data_hora(d.concluida_em)}",
                ),
            ],
        )

    # --- Custos -----------------------------------------------------------------------

    def _custos(self, d) -> ft.Control:
        """Previsto, Realizado e Diferença por categoria e no total (números do serviço).

        Tela larga: uma tabela. Celular: um cartão pequeno por categoria.
        """
        resumo = d.resumo_custos
        com_realizado = _tem_fase(d, custos.FASE_REALIZADO)
        linhas = [
            (
                c.categoria_nome,
                c.previsto_centavos,
                c.realizado_centavos,
                c.diferenca_centavos,
                c.diferenca_percentual,
            )
            for c in resumo.por_categoria
        ]
        total = (
            "Total",
            resumo.total_previsto_centavos,
            resumo.total_realizado_centavos,
            resumo.diferenca_centavos,
            resumo.diferenca_percentual,
        )

        def textos(linha) -> tuple[str, str, str]:
            _nome, previsto, realizado, diferenca, pct = linha
            if not com_realizado:
                return formatacao.formatar_brl(previsto), "-", "-"
            return (
                formatacao.formatar_brl(previsto),
                formatacao.formatar_brl(realizado),
                historico.texto_diferenca_valor(diferenca, pct),
            )

        if self.app._e_largo():
            corpo = [self._linha_tabela(("Categoria", "Previsto", "Realizado", "Diferença"), True)]
            for linha in [*linhas, total]:
                corpo.append(ft.Divider(height=1, thickness=1, color=theme.COR_CONTORNO))
                corpo.append(self._linha_tabela((linha[0], *textos(linha)), linha is total))
            return self._secao("Custos", corpo)
        pequenos = []
        for linha in [*linhas, total]:
            previsto, realizado, diferenca = textos(linha)
            pequenos.append(
                ft.Container(
                    bgcolor=theme.COR_CAMPO_FUNDO,
                    border_radius=theme.RAIO_BOTAO,
                    padding=theme.ESPACO_P + 4,
                    content=basicos.coluna(
                        [
                            basicos.titulo(linha[0], theme.FONTE_CORPO),
                            basicos.rotulo_valor("Previsto", previsto),
                            basicos.rotulo_valor("Realizado", realizado),
                            basicos.rotulo_valor("Diferença", diferenca),
                        ],
                        espaco=theme.ESPACO_P,
                    ),
                )
            )
        return self._secao("Custos", pequenos)

    @staticmethod
    def _linha_tabela(celulas: tuple[str, str, str, str], destaque: bool) -> ft.Control:
        peso = ft.FontWeight.BOLD if destaque else ft.FontWeight.NORMAL
        larguras = (3, 2, 2, 4)
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

    def _itens(self, d, fase: str) -> ft.Control:
        """Itens de uma fase, recolhidos por padrão."""
        itens = [i for i in d.itens if i.fase == fase]
        nome = "Itens previstos" if fase == custos.FASE_PREVISTO else "Itens realizados"
        linhas = [
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                i.descricao, color=theme.COR_TITULO, size=theme.FONTE_SUBTITULO
                            ),
                            ft.Text(
                                f"{i.categoria_nome}  ·  "
                                f"{formatacao.formatar_quantidade(i.quantidade)} x "
                                f"{formatacao.formatar_brl(i.valor_unitario_centavos)}",
                                color=theme.COR_SUBTITULO,
                                size=theme.FONTE_PEQUENA,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Text(
                        formatacao.formatar_brl(i.total_centavos),
                        color=theme.COR_TITULO,
                        size=theme.FONTE_SUBTITULO,
                    ),
                ]
            )
            for i in itens
        ]
        return basicos.cartao(
            ft.ExpansionTile(
                title=ft.Text(
                    f"{nome} ({len(itens)})",
                    color=theme.COR_TITULO,
                    size=theme.FONTE_CORPO,
                    weight=ft.FontWeight.BOLD,
                ),
                controls=linhas,
                expanded_cross_axis_alignment=ft.CrossAxisAlignment.STRETCH,
                text_color=theme.COR_TITULO,
                collapsed_text_color=theme.COR_TITULO,
                icon_color=theme.COR_SUBTITULO,
                collapsed_icon_color=theme.COR_SUBTITULO,
            )
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


def _tem_fase(d, fase: str) -> bool:
    return any(i.fase == fase for i in d.itens)


def _linha_do_tempo(d) -> list[ft.Control]:
    """Aberta em, Início, e Concluída em ou Cancelada em (só o que já aconteceu)."""
    linhas = [("Aberta em", d.aberta_em), ("Início da execução", d.inicio_execucao_em)]
    if d.cancelada_em is not None:
        linhas.append(("Cancelada em", d.cancelada_em))
    else:
        linhas.append(("Concluída em", d.concluida_em))
    return [
        basicos.rotulo_valor(
            rotulo, formatacao.formatar_data_hora(instante) if instante else "Ainda não"
        )
        for rotulo, instante in linhas
    ]


def _cartao_nota(nota: str, titulo: str) -> ft.Control:
    """A nota de conclusão em destaque."""
    return ft.Container(
        bgcolor=theme.COR_AVISO_FUNDO,
        border_radius=theme.RAIO_CARTAO,
        padding=theme.ESPACO_M,
        content=basicos.coluna(
            [
                ft.Row(
                    [
                        ft.Icon(ft.Icons.CHAT_OUTLINED, color=theme.COR_AVISO_TEXTO),
                        ft.Text(
                            titulo,
                            color=theme.COR_AVISO_TEXTO,
                            size=theme.FONTE_CORPO,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ],
                    spacing=theme.ESPACO_P,
                ),
                ft.Text(nota, color=theme.COR_TITULO, size=theme.FONTE_CORPO, selectable=True),
            ],
            espaco=theme.ESPACO_P,
        ),
    )
