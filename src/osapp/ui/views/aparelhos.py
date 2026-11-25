"""Perfil > 'Aparelhos conectados' (prompt 35; layout refeito no prompt 43).

Quem decide é services/sessoes_lembradas.py (só as famílias do próprio usuário).

Prompt 43: o cartão crescia para um retângulo cinza vazio. Causa: cada linha era um
``ft.Row(wrap=True)`` com uma ``ft.Column(expand=True)`` dentro. No Flet 1.1.2 a Row marca
``host_expanded`` mesmo com ``wrap=True``, então o filho com ``expand`` vira um ``Expanded``
do Flutter dentro de um ``Wrap`` (que não é um ``Flex``); a compilação web de produção
desenha um controle que falha assim como uma caixa cinza. Agora as linhas ficam numa
``ft.Column`` simples, sem ``expand`` e sem rolagem própria (a página já rola), e nenhuma
Row que quebra linha tem filho com ``expand`` (docs/REGRAS.md, 'Layout').
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import flet as ft

from osapp import formatacao
from osapp.services import sessoes_lembradas
from osapp.ui import theme
from osapp.ui.components import basicos
from osapp.ui.components.secao import SecaoCard

logger = logging.getLogger(__name__)

TITULO = "Aparelhos conectados"
NENHUM = 'Nenhum aparelho lembrado. Marque "Lembrar de mim" ao entrar para aparecer aqui.'
ESTE = "Este aparelho"
SAIR_DESTE = "Sair deste aparelho"
SAIR_DE_TODOS = "Sair de todos os aparelhos"
FALHA_LINHA = "Não foi possível mostrar este aparelho."
LIMITE = 10  # acima disso, os 10 mais recentes e 'Ver todos (N)'

# Tipo do aparelho pelo sistema no rótulo ('Chrome em Android'); só para o ícone.
TIPO_CELULAR = "celular"
TIPO_TABLET = "tablet"
TIPO_COMPUTADOR = "computador"
_SISTEMAS_CELULAR = ("Android", "iPhone")
_SISTEMAS_TABLET = ("iPad",)
_ICONES = {
    TIPO_CELULAR: ft.Icons.SMARTPHONE,
    TIPO_TABLET: ft.Icons.TABLET,
    TIPO_COMPUTADOR: ft.Icons.COMPUTER,
}


@dataclass(frozen=True)
class LinhaAparelho:
    familia: str
    rotulo: str
    tipo: str
    conectado: str  # 'Conectado em dd/mm/aaaa'
    ultimo_uso: str  # 'Último uso dd/mm/aaaa HH:MM'
    atual: bool


@dataclass(frozen=True)
class ConteudoAparelhos:
    linhas: tuple[LinhaAparelho, ...]
    vazio: str | None  # a frase quando não há aparelho
    ver_todos: str | None  # 'Ver todos (15)' quando há mais que LIMITE e está recolhido
    sair_de_todos: bool  # o botão só aparece com pelo menos um aparelho


def tipo_do_aparelho(rotulo: str) -> str:
    """'Chrome em Android' -> 'celular'. Função pura (testada)."""
    sistema = rotulo.rsplit(" em ", 1)[-1] if " em " in rotulo else ""
    if sistema in _SISTEMAS_CELULAR:
        return TIPO_CELULAR
    if sistema in _SISTEMAS_TABLET:
        return TIPO_TABLET
    return TIPO_COMPUTADOR


def linha_do_aparelho(aparelho, atual: bool) -> LinhaAparelho:
    """Os textos de uma linha (datas no fuso OS_TZ). Função pura (testada)."""
    return LinhaAparelho(
        familia=aparelho.familia,
        rotulo=aparelho.rotulo,
        tipo=tipo_do_aparelho(aparelho.rotulo),
        conectado=f"Conectado em {formatacao.formatar_data(aparelho.criado_em)}",
        ultimo_uso=f"Último uso {formatacao.formatar_data_hora(aparelho.ultimo_uso_em)}",
        atual=atual,
    )


def preparar(
    aparelhos, familia_atual: str | None, expandido: bool = False, limite: int = LIMITE
) -> ConteudoAparelhos:
    """O que o cartão mostra. Mais recentes primeiro (último uso). Função pura (testada)."""
    ordenados = sorted(aparelhos, key=lambda a: a.ultimo_uso_em, reverse=True)
    if not ordenados:
        return ConteudoAparelhos((), NENHUM, None, False)
    mostrar = ordenados if expandido else ordenados[:limite]
    ver_todos = None if len(mostrar) == len(ordenados) else f"Ver todos ({len(ordenados)})"
    linhas = tuple(linha_do_aparelho(a, a.familia == familia_atual) for a in mostrar)
    return ConteudoAparelhos(linhas, None, ver_todos, True)


def _atualizar(controle) -> None:
    try:
        controle.update()
    except RuntimeError:
        pass


class SecaoAparelhos:
    def __init__(self, app) -> None:
        self.app = app
        self.aparelhos: list = []
        self.expandido = False
        # Coluna simples: sem expand e sem scroll (a página já rola). O cartão tem a
        # altura do cabeçalho mais as linhas.
        self.lista = basicos.coluna([basicos.carregando()], espaco=theme.ESPACO_P)
        self.botao_todos = basicos.botao_secundario(
            SAIR_DE_TODOS, ft.Icons.LOGOUT, self._perguntar_todos
        )
        self.botao_todos.visible = False
        self.controle = SecaoCard(
            None, ft.Icons.DEVICES_OTHER_OUTLINED, TITULO, [self.lista, self.botao_todos]
        ).controle

    async def carregar(self) -> None:
        resultado = await self.app.chamar(
            sessoes_lembradas.listar_aparelhos, self.app.sessao.ator_id
        )
        if not resultado.ok:
            return
        self.aparelhos = list(resultado.valor)
        self._desenhar()

    def _desenhar(self) -> None:
        conteudo = preparar(self.aparelhos, self.app.familia_lembrada, self.expandido)
        controles: list[ft.Control] = []
        if conteudo.vazio is not None:
            controles.append(basicos.subtitulo(conteudo.vazio))
        for i, linha in enumerate(conteudo.linhas):
            if i:
                controles.append(ft.Divider(height=1, thickness=1, color=theme.COR_CONTORNO))
            controles.append(self._linha_segura(linha))
        if conteudo.ver_todos is not None:
            controles.append(
                ft.TextButton(
                    content=conteudo.ver_todos,
                    icon=ft.Icons.EXPAND_MORE,
                    style=theme.estilo_botao_texto(),
                    height=theme.ALVO_TOQUE_MIN,
                    on_click=self._ver_todos,
                )
            )
        self.lista.controls = controles
        self.botao_todos.visible = conteudo.sair_de_todos
        _atualizar(self.controle)

    def _ver_todos(self, _e=None) -> None:
        self.expandido = True
        self._desenhar()

    def _linha_segura(self, linha: LinhaAparelho) -> ft.Control:
        """Um erro ao montar uma linha vira uma frase no cartão (e vai para o log do
        servidor); nunca apaga o cartão nem a página."""
        try:
            return self._linha(linha)
        except Exception:  # noqa: BLE001 - uma linha nunca derruba o cartão
            logger.exception("Falha ao montar a linha de um aparelho lembrado.")
            return basicos.subtitulo(FALHA_LINHA)

    def _linha(self, linha: LinhaAparelho) -> ft.Control:
        async def sair(_e=None, familia=linha.familia) -> None:
            r = await self.app.chamar(
                sessoes_lembradas.sair_deste_aparelho, self.app.sessao.ator_id, familia
            )
            if r.ok:
                if familia == self.app.familia_lembrada:
                    await self.app.esquecer_token()
                self.app.avisar("Aparelho desconectado.")
                await self.carregar()

        titulo: list[ft.Control] = [
            ft.Text(
                linha.rotulo,
                color=theme.COR_TITULO,
                size=theme.FONTE_CORPO,
                weight=ft.FontWeight.BOLD,
            )
        ]
        if linha.atual:
            titulo.append(basicos.selo(ESTE, *theme.COR_STATUS_ABERTA))
        # Row SEM wrap: o único filho com expand fica num Flex de verdade. O botão vai
        # embaixo dos textos, para caber em 390 px sem apertar o rótulo.
        return ft.Row(
            [
                ft.Icon(_ICONES[linha.tipo], color=theme.COR_SUBTITULO),
                ft.Column(
                    [
                        ft.Row(titulo, spacing=theme.ESPACO_P, wrap=True),
                        basicos.subtitulo(linha.conectado),
                        basicos.subtitulo(linha.ultimo_uso),
                        ft.TextButton(
                            content=SAIR_DESTE,
                            icon=ft.Icons.LOGOUT,
                            style=theme.estilo_botao_texto(),
                            height=theme.ALVO_TOQUE_MIN,
                            on_click=sair,
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            spacing=theme.ESPACO_M,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def _perguntar_todos(self, _e=None) -> None:
        async def todos() -> None:
            r = await self.app.chamar(sessoes_lembradas.sair_de_todos, self.app.sessao.ator_id)
            if r.ok:
                await self.app.esquecer_token()
                self.app.avisar("Todos os aparelhos foram desconectados.")
                await self.carregar()

        self.app.confirmar(
            "Sair de todos os aparelhos?",
            "Todos os aparelhos lembrados vão pedir a senha de novo. Esta sessão continua "
            "aberta até você sair.",
            "Sair de todos",
            todos,
        )
