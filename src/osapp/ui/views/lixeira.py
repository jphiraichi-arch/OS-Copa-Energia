"""Lixeira (/lixeira e /lixeira/{id}), só para o administrador (aberta pelo Perfil).

A tela mostra o que o serviço devolver; quem pode ver e restaurar é decidido em
services/lixeira.py (os demais papéis recebem a recusa genérica).
"""

from __future__ import annotations

import flet as ft

from osapp import formatacao
from osapp.services import lixeira
from osapp.services.erros import ErroConflito, ErroNaoEncontrado, ErroPermissao
from osapp.ui import historico, rotas, rotulos, textos, theme
from osapp.ui.components import basicos
from osapp.ui.components.secao import secao
from osapp.ui.views.base import Tela


class Lixeira(Tela):
    banner = (ft.Icons.DELETE_OUTLINE, textos.LIXEIRA_TITULO)

    def __init__(self, app, **_params) -> None:
        self.app = app
        self.pagina = 1
        self.itens: list = []
        self.busca = basicos.campo_texto(
            textos.LIXEIRA_BUSCA,
            hint_text="Número, título, descrição ou itens",
            on_submit=self._buscar,
        )
        self.lista = basicos.coluna([], espaco=theme.ESPACO_M)
        self.rodape = basicos.coluna([])
        self.conteudo = basicos.coluna([self.busca, self.lista, self.rodape])

    async def carregar(self) -> None:
        await self._buscar()

    async def _buscar(self, _e=None) -> None:
        self.pagina, self.itens = 1, []
        await self._pagina()

    async def _mais(self, _e=None) -> None:
        self.pagina += 1
        await self._pagina()

    async def _pagina(self) -> None:
        self.rodape.controls = [basicos.carregando()]
        self._atualizar()
        resultado = await self.app.chamar(
            lixeira.listar_excluidas,
            self.app.sessao.ator_id,
            (self.busca.value or "").strip() or None,
            self.pagina,
            erros_tratados=(ErroPermissao,),
        )
        self.rodape.controls = []
        if isinstance(resultado.erro, ErroPermissao):
            self.lista.controls = [basicos.mensagem_central(self.app.MENSAGEM_GENERICA)]
        elif resultado.ok:
            self.itens.extend(resultado.valor.itens)
            self.lista.controls = [self._cartao(i) for i in self.itens]
            if not self.itens:
                self.rodape.controls = [basicos.mensagem_central(textos.LIXEIRA_VAZIA)]
            elif resultado.valor.tem_mais:
                self.rodape.controls = [
                    basicos.botao_secundario("Carregar mais", ft.Icons.EXPAND_MORE, self._mais)
                ]
        self._atualizar()

    def _atualizar(self) -> None:
        try:
            self.conteudo.update()
        except RuntimeError:
            pass  # a tela já foi trocada

    def _cartao(self, i) -> ft.Control:
        async def abrir(_e=None, os_id=i.id) -> None:
            await self.app.ir(rotas.rota_lixeira(os_id))

        return basicos.cartao(
            basicos.coluna(
                [
                    ft.Row(
                        [
                            ft.Text(
                                i.numero, color=theme.COR_SUBTITULO, size=theme.FONTE_SUBTITULO
                            ),
                            basicos.selo_status(i.status),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Text(
                        i.titulo,
                        color=theme.COR_TITULO,
                        size=theme.FONTE_CORPO,
                        weight=ft.FontWeight.BOLD,
                    ),
                    basicos.subtitulo(
                        f"Excluída em {formatacao.formatar_data_hora(i.excluida_em)} por "
                        f"{i.excluida_por_nome}  ·  {i.filial_codigo}"
                    ),
                    basicos.rotulo_valor("Motivo", i.motivo),
                ],
                espaco=6,
            ),
            on_click=abrir,
        )


class LixeiraDetalhe(Tela):
    """Detalhe só de leitura, com a faixa 'Ordem excluída' e o botão 'Restaurar'."""

    def __init__(self, app, os_id: int, **_params) -> None:
        self.app = app
        self.os_id = os_id
        self.dados = None
        self.conteudo = basicos.coluna([basicos.carregando()])

    async def carregar(self) -> None:
        resultado = await self.app.chamar(
            lixeira.obter_excluida,
            self.app.sessao.ator_id,
            self.os_id,
            erros_tratados=(ErroPermissao, ErroNaoEncontrado),
        )
        if resultado.ok:
            self.dados = resultado.valor
            self.conteudo.controls = self._montar(resultado.valor)
        elif isinstance(resultado.erro, ErroNaoEncontrado):
            self.conteudo.controls = [basicos.mensagem_central("Ordem não está na Lixeira.")]
        else:
            self.conteudo.controls = [basicos.mensagem_central(self.app.MENSAGEM_GENERICA)]
        try:
            self.conteudo.update()
        except RuntimeError:
            pass

    def _montar(self, x) -> list[ft.Control]:
        d = x.os
        faixa = ft.Container(
            bgcolor=theme.COR_ERRO,
            border_radius=theme.RAIO_CARTAO,
            padding=theme.ESPACO_M,
            content=basicos.coluna(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.DELETE_OUTLINE, color=theme.COR_SOBRE_ERRO),
                            ft.Text(
                                textos.LIXEIRA_FAIXA,
                                color=theme.COR_SOBRE_ERRO,
                                size=theme.FONTE_TITULO,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        spacing=theme.ESPACO_P,
                    ),
                    ft.Text(
                        f"Em {formatacao.formatar_data_hora(x.excluida_em)}, por "
                        f"{x.excluida_por_nome}. Motivo: {x.motivo}",
                        color=theme.COR_SOBRE_ERRO,
                        size=theme.FONTE_CORPO,
                    ),
                ],
                espaco=theme.ESPACO_P,
            ),
        )
        resumo = secao(
            None,
            ft.Icons.DESCRIPTION_OUTLINED,
            f"{d.numero} · {rotulos.status(d.status)}",
            [
                basicos.titulo(d.titulo),
                basicos.rotulo_valor("Descrição", d.descricao),
                basicos.rotulo_valor("Filial", f"{d.filial_codigo} - {d.filial_nome}"),
                basicos.rotulo_valor(
                    "Criada por",
                    f"{d.criado_por_nome}, em {formatacao.formatar_data_hora(d.criado_em)}",
                ),
                basicos.rotulo_valor(
                    "Previsto",
                    formatacao.formatar_brl(d.resumo_custos.total_previsto_centavos),
                ),
            ],
        )
        eventos = [
            basicos.rotulo_valor(
                f"{formatacao.formatar_data_hora(e.data_hora)}  ·  {e.nome_usuario}",
                historico.frase(e),
            )
            for e in reversed(x.eventos)
        ]
        return [
            faixa,
            basicos.botao_primario(textos.LIXEIRA_RESTAURAR, ft.Icons.RESTORE, self._perguntar),
            resumo,
            secao(None, ft.Icons.HISTORY, "Histórico", eventos),
        ]

    def _perguntar(self, _e=None) -> None:
        self.app.confirmar(
            "Restaurar Ordem de Serviço?",
            "Ela volta para as listas, a busca, os contadores e os relatórios, com o mesmo número.",
            textos.LIXEIRA_RESTAURAR,
            self._restaurar,
            rotulo_cancelar="Voltar",
        )

    async def _restaurar(self) -> None:
        resultado = await self.app.chamar(
            lixeira.restaurar_os,
            self.app.sessao.ator_id,
            self.os_id,
            self.dados.os.versao,
            erros_tratados=(ErroConflito, ErroPermissao, ErroNaoEncontrado),
        )
        if resultado.ok:
            await self.app.atualizar_contadores()
            await self.app.ir(
                rotas.rota_os(self.os_id),
                mensagem=f"Ordem de Serviço {resultado.valor.numero} restaurada.",
            )
        elif isinstance(resultado.erro, ErroConflito):
            self.app.avisar(
                "Esta Ordem de Serviço foi alterada por outra pessoa. Atualize e tente novamente."
            )
        else:
            self.app.avisar(self.app.MENSAGEM_GENERICA)
