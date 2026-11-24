"""Perfil > 'Aparelhos conectados' (prompt 35): os 'Lembrar de mim' ativos do usuário.

Quem decide é services/sessoes_lembradas.py (só as famílias do próprio usuário).
"""

from __future__ import annotations

import flet as ft

from osapp import formatacao
from osapp.services import sessoes_lembradas
from osapp.ui import theme
from osapp.ui.components import basicos
from osapp.ui.components.secao import SecaoCard

TITULO = "Aparelhos conectados"
NENHUM = "Nenhum aparelho lembrado. Marque 'Lembrar de mim por 7 dias' ao entrar."
ESTE = "este aparelho"


def linha_do_aparelho(aparelho, atual: bool) -> str:
    """'Chrome em Android (este aparelho)'. Função pura (testada)."""
    return f"{aparelho.rotulo} ({ESTE})" if atual else aparelho.rotulo


def _atualizar(controle) -> None:
    try:
        controle.update()
    except RuntimeError:
        pass


class SecaoAparelhos:
    def __init__(self, app) -> None:
        self.app = app
        self.lista = basicos.coluna([basicos.carregando()], espaco=theme.ESPACO_P)
        self.botao_todos = basicos.botao_secundario(
            "Sair de todos os aparelhos", ft.Icons.LOGOUT, self._perguntar_todos
        )
        self.controle = SecaoCard(
            None, ft.Icons.DEVICES_OTHER_OUTLINED, TITULO, [self.lista, self.botao_todos]
        ).controle

    async def carregar(self) -> None:
        resultado = await self.app.chamar(
            sessoes_lembradas.listar_aparelhos, self.app.sessao.ator_id
        )
        if not resultado.ok:
            return
        aparelhos = resultado.valor
        self.lista.controls = [self._linha(a) for a in aparelhos] or [basicos.subtitulo(NENHUM)]
        self.botao_todos.visible = bool(aparelhos)
        _atualizar(self.controle)

    def _linha(self, a) -> ft.Control:
        atual = a.familia == self.app.familia_lembrada

        async def sair(_e=None, familia=a.familia) -> None:
            r = await self.app.chamar(
                sessoes_lembradas.sair_deste_aparelho, self.app.sessao.ator_id, familia
            )
            if r.ok:
                if familia == self.app.familia_lembrada:
                    await self.app.esquecer_token()
                self.app.avisar("Aparelho desconectado.")
                await self.carregar()

        return ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(
                            linha_do_aparelho(a, atual),
                            color=theme.COR_TITULO,
                            size=theme.FONTE_CORPO,
                            weight=ft.FontWeight.BOLD,
                        ),
                        basicos.subtitulo(
                            f"Desde {formatacao.formatar_data_hora(a.criado_em)}  ·  "
                            f"último uso {formatacao.formatar_data_hora(a.ultimo_uso_em)}"
                        ),
                    ],
                    spacing=2,
                    expand=True,
                ),
                ft.TextButton(
                    content="Sair deste aparelho",
                    style=theme.estilo_botao_texto(),
                    height=theme.ALVO_TOQUE_MIN,
                    on_click=sair,
                ),
            ],
            wrap=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
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
