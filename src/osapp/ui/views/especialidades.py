"""Perfil > Especialidades (prompt 37, só administrador): criar, renomear, desativar e
reordenar. Quem decide é services/especialidades.py."""

from __future__ import annotations

import flet as ft

from osapp.services import especialidades
from osapp.services.erros import ErroPermissao
from osapp.ui import theme
from osapp.ui.components import basicos
from osapp.ui.views.base import Tela

TITULO = "Especialidades"
AJUDA = (
    "Quem atende cada Ordem de Serviço. Uma especialidade desativada não aparece em OS "
    "novas, mas continua nas antigas."
)


def _atualizar(controle) -> None:
    try:
        controle.update()
    except RuntimeError:
        pass


class Especialidades(Tela):
    def __init__(self, app, **_params) -> None:
        self.app = app
        self.nova = basicos.campo_texto(
            "Nova especialidade", max_length=especialidades.NOME_MAX, on_submit=self._criar
        )
        self.lista = basicos.coluna([basicos.carregando()], espaco=theme.ESPACO_P)
        self.conteudo = basicos.coluna(
            [
                basicos.titulo(TITULO, theme.FONTE_SAUDACAO),
                basicos.subtitulo(AJUDA),
                basicos.cartao(
                    basicos.coluna(
                        [self.nova, basicos.botao_primario("Adicionar", ft.Icons.ADD, self._criar)]
                    )
                ),
                self.lista,
            ]
        )

    async def carregar(self) -> None:
        r = await self.app.chamar(
            especialidades.listar, self.app.sessao.ator_id, True, erros_tratados=(ErroPermissao,)
        )
        if not r.ok:
            self.conteudo.controls = [basicos.mensagem_central(self.app.MENSAGEM_GENERICA)]
        else:
            self.lista.controls = [self._linha(e, i, len(r.valor)) for i, e in enumerate(r.valor)]
        _atualizar(self.conteudo)

    def _linha(self, e, posicao: int, total: int) -> ft.Control:
        nome = basicos.campo_texto("Nome", value=e.nome, max_length=especialidades.NOME_MAX)

        async def salvar(_ev=None) -> None:
            r = await self.app.chamar(
                especialidades.alterar,
                self.app.sessao.ator_id,
                e.id,
                nome.value or "",
                campos={"nome": nome},
            )
            if r.ok:
                self.app.avisar("Especialidade salva.")

        async def ativar(_ev=None) -> None:
            r = await self.app.chamar(
                especialidades.alterar, self.app.sessao.ator_id, e.id, None, not e.ativo
            )
            if r.ok:
                await self.carregar()

        async def mover(direcao: int) -> None:
            r = await self.app.chamar(especialidades.mover, self.app.sessao.ator_id, e.id, direcao)
            if r.ok:
                await self.carregar()

        def botao(icone, dica, acao, habilitado=True):
            return ft.IconButton(
                icon=icone,
                icon_color=theme.COR_BOTAO_PRIMARIO,
                tooltip=dica,
                width=theme.ALVO_TOQUE_MIN,
                height=theme.ALVO_TOQUE_MIN,
                disabled=not habilitado,
                on_click=acao,
            )

        situacao = (
            basicos.selo("Ativa", *theme.COR_STATUS_CONCLUIDA)
            if e.ativo
            else basicos.selo("Desativada", *theme.COR_STATUS_CANCELADA)
        )
        return basicos.cartao(
            basicos.coluna(
                [
                    ft.Row([situacao, basicos.subtitulo(e.codigo)], spacing=theme.ESPACO_P),
                    nome,
                    ft.Row(
                        [
                            botao(ft.Icons.SAVE_OUTLINED, "Salvar nome", salvar),
                            botao(
                                ft.Icons.ARROW_UPWARD,
                                "Subir",
                                lambda _ev: self.app.page.run_task(mover, -1),
                                posicao > 0,
                            ),
                            botao(
                                ft.Icons.ARROW_DOWNWARD,
                                "Descer",
                                lambda _ev: self.app.page.run_task(mover, 1),
                                posicao < total - 1,
                            ),
                            ft.TextButton(
                                content="Desativar" if e.ativo else "Reativar",
                                style=theme.estilo_botao_texto(),
                                height=theme.ALVO_TOQUE_MIN,
                                on_click=ativar,
                            ),
                        ],
                        wrap=True,
                    ),
                ],
                espaco=theme.ESPACO_P,
            )
        )

    async def _criar(self, _e=None) -> None:
        r = await self.app.chamar(
            especialidades.criar,
            self.app.sessao.ator_id,
            self.nova.value or "",
            campos={"nome": self.nova},
        )
        if r.ok:
            self.nova.value = ""
            self.app.avisar("Especialidade criada.")
            await self.carregar()
