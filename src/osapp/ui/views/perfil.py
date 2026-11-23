"""Perfil (/perfil) e Alterar senha (/perfil/senha).

Perfil reúne o que ficava no menu de três barras: Configurações, Alterar senha,
Usuários (administrador) e Sair. Esconder 'Usuários' é conveniência: o serviço de
usuários já recusa quem não é administrador.
"""

from __future__ import annotations

import flet as ft

from osapp.ui import rotas, rotulos, textos, theme
from osapp.ui.components import basicos
from osapp.ui.views.base import Tela
from osapp.ui.views.senha import cartao_alterar_senha


def itens_do_perfil(papel: str) -> tuple[str, ...]:
    """Chaves das entradas do Perfil, na ordem. Função pura (testada).

    O administrador também tem 'Nova Solicitação' aqui: na barra inferior, 'Nova OS'
    abre a Ordem de Serviço completa para ele.
    """
    itens = ["configuracoes", "alterar_senha"]
    if papel == "admin":
        itens += ["usuarios", "nova_solicitacao"]
    return (*itens, "sair")


_ENTRADAS = {
    "configuracoes": (textos.MENU_CONFIGURACOES, ft.Icons.SETTINGS_OUTLINED, rotas.CONFIGURACOES),
    "alterar_senha": (textos.MENU_ALTERAR_SENHA, ft.Icons.LOCK_RESET, rotas.ALTERAR_SENHA),
    "usuarios": (textos.MENU_USUARIOS, ft.Icons.GROUP_OUTLINED, rotas.USUARIOS),
    "nova_solicitacao": (
        textos.MENU_NOVA_SOLICITACAO,
        ft.Icons.ADD_COMMENT_OUTLINED,
        rotas.SOLICITACAO_NOVA,
    ),
    "sair": (textos.MENU_SAIR, ft.Icons.LOGOUT, None),
}


class Perfil(Tela):
    banner = (ft.Icons.PERSON, textos.PERFIL_TITULO)

    def __init__(self, app, **_params) -> None:
        self.app = app
        sessao = app.sessao
        quem = basicos.cartao(
            basicos.coluna(
                [
                    basicos.titulo(sessao.nome),
                    basicos.subtitulo(f"{sessao.login}  ·  {rotulos.papel(sessao.papel)}"),
                ],
                espaco=4,
            )
        )
        linhas: list[ft.Control] = []
        for chave in itens_do_perfil(sessao.papel):
            rotulo, icone, rota = _ENTRADAS[chave]
            if linhas:
                linhas.append(ft.Divider(height=1, thickness=1, color=theme.COR_CONTORNO))
            linhas.append(self._linha(rotulo, icone, rota))
        self.conteudo = basicos.coluna(
            [quem, basicos.cartao(ft.Column(linhas, spacing=0))], espaco=theme.ESPACO_M
        )

    def _linha(self, rotulo: str, icone: ft.IconData, rota: str | None) -> ft.Control:
        async def abrir(_e=None) -> None:
            if rota is None:
                await self.app.sair()
            else:
                await self.app.ir(rota)

        return ft.Container(
            height=theme.ALVO_TOQUE_MIN + 8,
            ink=True,
            on_click=abrir,
            padding=ft.Padding.symmetric(horizontal=theme.ESPACO_P),
            content=ft.Row(
                [
                    ft.Icon(icone, color=theme.COR_PRIMARIO),
                    ft.Text(rotulo, color=theme.COR_TITULO, size=theme.FONTE_CORPO, expand=True),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=theme.COR_SUBTITULO),
                ],
                spacing=theme.ESPACO_M,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )


class AlterarSenha(Tela):
    """O cartão de troca de senha (o mesmo de antes), numa tela própria."""

    def __init__(self, app, **_params) -> None:
        self.app = app
        self.conteudo = basicos.coluna(
            [
                basicos.titulo(textos.MENU_ALTERAR_SENHA, theme.FONTE_SAUDACAO),
                cartao_alterar_senha(app),
            ]
        )
