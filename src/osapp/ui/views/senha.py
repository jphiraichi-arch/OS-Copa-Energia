"""Troca da própria senha: tela obrigatória (/trocar-senha) e cartão em Configurações."""

from __future__ import annotations

import flet as ft

from osapp.services import usuarios
from osapp.ui import rotas, theme
from osapp.ui.components import basicos
from osapp.ui.views.base import Tela

TITULO_OBRIGATORIA = "Crie uma nova senha"
AVISO_OBRIGATORIA = (
    "Sua senha é temporária. Para continuar, escolha uma senha nova que só você saiba."
)
TITULO_CARTAO = "Alterar senha"
MSG_CONFIRMACAO = "A confirmação não é igual à nova senha."
MSG_SUCESSO = "Senha alterada."


class FormularioSenha:
    """Senha atual, nova e confirmação, com a regra na tela. O serviço valida de novo."""

    def __init__(self, app, rotulo_botao: str, ao_concluir) -> None:
        self.app = app
        self._ao_concluir = ao_concluir
        opcoes = {"password": True, "can_reveal_password": True, "on_change": self._limpar}
        self.atual = basicos.campo_texto("Senha atual", **opcoes)
        self.nova = basicos.campo_texto("Nova senha", **opcoes)
        self.confirmacao = basicos.campo_texto("Repita a nova senha", **opcoes)
        self.botao = basicos.botao_primario(rotulo_botao, ft.Icons.LOCK_RESET, self._salvar)
        self.campos = {"senha_atual": self.atual, "senha": self.nova}
        self.controle = basicos.coluna(
            [
                self.atual,
                self.nova,
                self.confirmacao,
                basicos.subtitulo(usuarios.MSG_REGRA_SENHA),  # a regra fica visível
                self.botao,
            ]
        )

    def _limpar(self, e) -> None:
        if e.control.error:
            e.control.error = None
            e.control.update()

    async def _salvar(self, _e=None) -> None:
        if self.botao.disabled:
            return
        if (self.nova.value or "") != (self.confirmacao.value or ""):
            self.confirmacao.error = MSG_CONFIRMACAO
            self.controle.update()
            return
        self.botao.disabled = True
        self.controle.update()
        try:
            resultado = await self.app.chamar(
                usuarios.trocar_propria_senha,
                self.app.sessao.ator_id,
                self.atual.value or "",
                self.nova.value or "",
                campos=self.campos,
            )
        finally:
            self.botao.disabled = False
        for campo in (self.atual, self.nova, self.confirmacao):
            campo.value = ""  # nunca deixar senha nos campos
        try:
            self.controle.update()
        except RuntimeError:
            pass
        if resultado.ok:
            await self._ao_concluir()


class TrocarSenha(Tela):
    """Tela obrigatória depois de um login com senha temporária. Nenhuma rota a pula
    (ui/sessao.decidir_rota manda para cá enquanto a troca estiver pendente)."""

    def __init__(self, app, **_params) -> None:
        self.app = app
        self.formulario = FormularioSenha(app, "Salvar nova senha", self._concluido)
        self.conteudo = ft.Container(
            alignment=ft.Alignment.TOP_CENTER,
            padding=ft.Padding.only(
                left=theme.ESPACO_M, right=theme.ESPACO_M, top=theme.ESPACO_G * 2
            ),
            content=ft.Container(
                max_width=theme.LARGURA_MAX_LOGIN,
                content=basicos.cartao(
                    basicos.coluna(
                        [
                            basicos.titulo(TITULO_OBRIGATORIA),
                            basicos.subtitulo(AVISO_OBRIGATORIA),
                            self.formulario.controle,
                            basicos.botao_secundario("Sair", ft.Icons.LOGOUT, app.sair),
                        ]
                    )
                ),
            ),
        )

    async def _concluido(self) -> None:
        self.app.sessao.troca_obrigatoria = False
        await self.app.ir(rotas.HOME, mensagem=MSG_SUCESSO)


def cartao_alterar_senha(app) -> ft.Control:
    """Cartão 'Alterar senha' de Configurações (todos os papéis)."""

    async def concluido() -> None:
        app.avisar(MSG_SUCESSO)

    formulario = FormularioSenha(app, "Alterar senha", concluido)
    return basicos.cartao(basicos.coluna([basicos.titulo(TITULO_CARTAO), formulario.controle]))
