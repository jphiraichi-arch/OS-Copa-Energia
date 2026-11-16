"""Tela de login."""

from __future__ import annotations

import flet as ft

from osapp.services import auth
from osapp.services.erros import ErroAutenticacao
from osapp.ui import theme
from osapp.ui.components import basicos
from osapp.ui.components.cabecalho import logo
from osapp.ui.views.base import Tela

MENSAGEM_CREDENCIAIS = "Usuário ou senha inválidos."


class Login(Tela):
    def __init__(self, app, **_params) -> None:
        self.app = app
        self.usuario = basicos.campo_texto(
            "Usuário",
            autofocus=True,
            max_length=auth.LOGIN_MAX,
            counter=" ",  # esconde o contador de caracteres
            on_submit=self._entrar,
        )
        self.senha = basicos.campo_texto(
            "Senha",
            password=True,
            can_reveal_password=True,
            on_submit=self._entrar,
        )
        self.mensagem = ft.Text(
            app.sessao.mensagem_login or "",
            color=theme.COR_ERRO,
            size=theme.FONTE_SUBTITULO,
            visible=bool(app.sessao.mensagem_login),
        )
        app.sessao.mensagem_login = None  # mostrada uma única vez
        self.botao = basicos.botao_primario("Entrar", ft.Icons.LOGIN, self._entrar)
        self.conteudo = ft.Container(
            alignment=ft.Alignment.TOP_CENTER,
            padding=ft.Padding.only(
                left=theme.ESPACO_M, right=theme.ESPACO_M, top=theme.ESPACO_G * 2
            ),
            content=ft.Container(
                max_width=theme.LARGURA_MAX_LOGIN,
                content=basicos.coluna(
                    [
                        ft.Row(
                            [logo(cor_texto=theme.COR_TITULO, escala=1.6)],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        basicos.cartao(
                            basicos.coluna(
                                [
                                    basicos.titulo("Entrar"),
                                    self.usuario,
                                    self.senha,
                                    self.mensagem,
                                    self.botao,
                                ]
                            )
                        ),
                    ],
                    espaco=theme.ESPACO_G,
                ),
            ),
        )

    async def _entrar(self, _e=None) -> None:
        if self.botao.disabled:
            return
        login, senha = self.usuario.value or "", self.senha.value or ""
        self.botao.disabled = True
        self.mensagem.visible = False
        self.conteudo.update()
        resultado = await self.app.chamar(
            auth.autenticar, login, senha, exige_sessao=False, erros_tratados=(ErroAutenticacao,)
        )
        self.senha.value = ""  # o campo de senha é limpo depois de toda tentativa
        self.botao.disabled = False
        if resultado.ok:
            await self.app.entrar(resultado.valor)
            return
        if isinstance(resultado.erro, ErroAutenticacao):
            self.mensagem.value = MENSAGEM_CREDENCIAIS
            self.mensagem.visible = True
        self.conteudo.update()
