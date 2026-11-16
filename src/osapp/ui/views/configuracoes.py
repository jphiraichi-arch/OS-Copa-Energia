"""Tela Configurações (/configuracoes): dados do usuário e do app, só para leitura.

É uma lista de cartões, para que novas configurações entrem depois como novos cartões.
"""

from __future__ import annotations

from importlib import metadata

import flet as ft

from osapp.services import ordens
from osapp.ui import textos, theme
from osapp.ui.components import basicos
from osapp.ui.views.base import Tela


def versao_do_app() -> str:
    try:
        return metadata.version("osapp")
    except metadata.PackageNotFoundError:
        return "desconhecida"


def rotulo_do_perfil(is_admin: bool) -> str:
    return textos.PERFIL_ADMINISTRADOR if is_admin else textos.PERFIL_USUARIO


class Configuracoes(Tela):
    def __init__(self, app, **_params) -> None:
        self.app = app
        sessao = app.sessao
        # O nome da filial vem do serviço em carregar(); até lá, mostra-se o código.
        self.filial = basicos.rotulo_valor(textos.CONFIG_FILIAL, sessao.filial_codigo)
        self.conteudo = basicos.coluna(
            [
                basicos.titulo(textos.CONFIG_TITULO, theme.FONTE_SAUDACAO),
                self._cartao(
                    textos.CONFIG_CARTAO_USUARIO,
                    ft.Icons.PERSON_OUTLINE,
                    [
                        basicos.rotulo_valor(textos.CONFIG_NOME, sessao.nome),
                        basicos.rotulo_valor(textos.CONFIG_LOGIN, sessao.login),
                        self.filial,
                        basicos.rotulo_valor(
                            textos.CONFIG_PERFIL, rotulo_do_perfil(sessao.is_admin)
                        ),
                    ],
                ),
                self._cartao(
                    textos.CONFIG_CARTAO_APLICATIVO,
                    ft.Icons.INFO_OUTLINE,
                    [basicos.rotulo_valor(textos.CONFIG_VERSAO, versao_do_app())],
                ),
            ]
        )

    def _cartao(self, nome: str, icone: ft.IconData, linhas: list[ft.Control]) -> ft.Control:
        return basicos.cartao(
            basicos.coluna(
                [
                    ft.Row(
                        [ft.Icon(icone, color=theme.COR_BOTAO_PRIMARIO), basicos.titulo(nome)],
                        spacing=theme.ESPACO_P,
                    ),
                    *linhas,
                ],
                espaco=theme.ESPACO_P + 4,
            )
        )

    async def carregar(self) -> None:
        """Busca o nome da filial no serviço (que só devolve as filiais que o ator pode ver)."""
        resultado = await self.app.chamar(ordens.listar_filiais, self.app.sessao.ator_id)
        if not resultado.ok:
            return
        for filial in resultado.valor:
            if filial.id == self.app.sessao.filial_id:
                self.filial.controls[1].value = f"{filial.codigo} - {filial.nome}"
                try:
                    self.filial.update()
                except RuntimeError:
                    pass  # a tela já foi trocada
