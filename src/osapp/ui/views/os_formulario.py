"""Telas Criar OS (/os/nova) e Alterar OS (/os/{id}/editar)."""

from __future__ import annotations

import flet as ft

from osapp.services import ordens
from osapp.services.erros import ErroConflito, ErroNaoEncontrado, ErroPermissao
from osapp.ui import rotas, theme
from osapp.ui.components import basicos
from osapp.ui.components.formulario_os import FormularioOs
from osapp.ui.views.base import Tela

MENSAGEM_CONFLITO = "Esta OS foi alterada por outra pessoa. Atualize e tente novamente."


class _TelaDeFormulario(Tela):
    titulo_da_tela = ""
    rotulo_do_botao = ""

    def __init__(self, app) -> None:
        self.app = app
        self.formulario: FormularioOs | None = None
        self.aviso = ft.Text("", color=theme.COR_ERRO, size=theme.FONTE_SUBTITULO, visible=False)
        self.botao = basicos.botao_primario(self.rotulo_do_botao, ft.Icons.SAVE, self._salvar)
        self.conteudo = basicos.coluna([basicos.carregando()])

    def tem_alteracoes(self) -> bool:
        return self.formulario is not None and self.formulario.tem_alteracoes()

    def _mostrar_formulario(self) -> None:
        self.conteudo.controls = [
            basicos.cartao(
                basicos.coluna(
                    [basicos.titulo(self.titulo_da_tela), self.formulario.controle, self.aviso]
                )
            ),
            self.botao,
        ]

    def _mostrar_mensagem(self, mensagem: str, rota_de_volta: str, rotulo: str) -> None:
        async def voltar(_e=None) -> None:
            await self.app.ir(rota_de_volta)

        self.conteudo.controls = [
            basicos.mensagem_central(mensagem),
            basicos.botao_secundario(rotulo, ft.Icons.ARROW_BACK, voltar),
        ]

    def _atualizar(self) -> None:
        try:
            self.conteudo.update()
        except RuntimeError:
            pass  # a tela já foi trocada

    async def _salvar(self, _e=None) -> None:
        if self.botao.disabled or self.formulario is None:
            return
        self.aviso.visible = False
        valores = self.formulario.ler()
        if valores is None:
            self._atualizar()
            return
        self.botao.disabled = True  # um toque duplo não grava duas vezes
        self._atualizar()
        try:
            await self._gravar(valores)
        finally:
            self.botao.disabled = False
            self._atualizar()

    async def _gravar(self, valores: dict) -> None:
        raise NotImplementedError


class CriarOs(_TelaDeFormulario):
    titulo_da_tela = "Nova OS"
    rotulo_do_botao = "Salvar OS"

    def __init__(self, app, **_params) -> None:
        super().__init__(app)

    async def carregar(self) -> None:
        resultado = await self.app.chamar(ordens.listar_filiais, self.app.sessao.ator_id)
        if resultado.ok:
            self.formulario = FormularioOs(self.app, resultado.valor)
            self._mostrar_formulario()
        else:
            self._mostrar_mensagem(
                "Não foi possível abrir o formulário.", rotas.HOME, "Voltar para a lista"
            )
        self._atualizar()

    async def _gravar(self, valores: dict) -> None:
        resultado = await self.app.chamar(
            ordens.criar_os,
            self.app.sessao.ator_id,
            valores["titulo"],
            valores["descricao"],
            valores["valor_previsto_centavos"],
            valores["tempo_previsto_minutos"],
            valores["filial_id"],
            campos=self.formulario.campos,
        )
        if resultado.ok:
            self.formulario.marcar_como_salvo()
            await self.app.ir(rotas.rota_os(resultado.valor.id), mensagem="OS criada.")


class EditarOs(_TelaDeFormulario):
    titulo_da_tela = "Alterar OS"
    rotulo_do_botao = "Salvar alterações"

    def __init__(self, app, os_id: int, **_params) -> None:
        super().__init__(app)
        self.os_id = os_id
        self.os = None

    async def carregar(self) -> None:
        ator_id = self.app.sessao.ator_id
        resultado = await self.app.chamar(
            ordens.obter_os, ator_id, self.os_id, erros_tratados=(ErroNaoEncontrado,)
        )
        if isinstance(resultado.erro, ErroNaoEncontrado):
            self._mostrar_mensagem("OS não encontrada.", rotas.HOME, "Voltar para a lista")
        elif resultado.ok and not resultado.valor.acoes.pode_editar:
            # A rota foi aberta sem permissão: o serviço diz que não pode (acoes).
            self._mostrar_mensagem(
                self.app.MENSAGEM_GENERICA, rotas.rota_os(self.os_id), "Voltar para a OS"
            )
        elif resultado.ok:
            filiais = await self.app.chamar(ordens.listar_filiais, ator_id)
            if filiais.ok:
                self.os = resultado.valor
                self.formulario = FormularioOs(
                    self.app,
                    filiais.valor,
                    os=self.os,
                    com_realizado=self.os.acoes.pode_editar_realizado,
                )
                self._mostrar_formulario()
        if self.formulario is None and len(self.conteudo.controls) == 1:
            # Nada foi mostrado ainda: a carga falhou (o aviso genérico já apareceu).
            self._mostrar_mensagem(
                "Não foi possível abrir o formulário.", rotas.HOME, "Voltar para a lista"
            )
        self._atualizar()

    async def _gravar(self, valores: dict) -> None:
        alteracoes = self.formulario.alteracoes(valores)
        destino = rotas.rota_os(self.os_id)
        if not alteracoes:
            self.formulario.marcar_como_salvo()
            await self.app.ir(destino, mensagem="Nenhuma alteração para salvar.")
            return
        resultado = await self.app.chamar(
            ordens.editar_os,
            self.app.sessao.ator_id,
            self.os_id,
            self.os.versao,
            alteracoes,
            campos=self.formulario.campos,
            erros_tratados=(ErroConflito, ErroPermissao, ErroNaoEncontrado),
        )
        if resultado.ok:
            self.formulario.marcar_como_salvo()
            await self.app.ir(destino, mensagem="OS alterada.")
        elif isinstance(resultado.erro, ErroConflito):
            self.aviso.value = MENSAGEM_CONFLITO
            self.aviso.visible = True
            self.app.avisar(MENSAGEM_CONFLITO)
        elif isinstance(resultado.erro, ErroPermissao | ErroNaoEncontrado):
            self.app.avisar(self.app.MENSAGEM_GENERICA)
