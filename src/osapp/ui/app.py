"""Casca do app: rotas, guarda de sessão, navegação e chamada de serviços.

Roteamento: abordagem imperativa da documentação ("Navigation and routing"):
``page.on_route_change`` reconstrói ``page.views`` a partir de ``page.route``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import flet as ft

from osapp.config import Config
from osapp.services import relogio
from osapp.services.erros import ErroAutenticacao, ErroValidacao
from osapp.ui import rotas, theme
from osapp.ui import sessao as sessao_ui
from osapp.ui.components import cabecalho
from osapp.ui.views.base import Tela
from osapp.ui.views.concluir import ConcluirOs
from osapp.ui.views.detalhe import Detalhe
from osapp.ui.views.home import Home
from osapp.ui.views.login import Login
from osapp.ui.views.os_formulario import CriarOs, EditarOs

logger = logging.getLogger(__name__)

MENSAGEM_GENERICA = "Não foi possível concluir a operação. Tente novamente."

# Destinos da navegação principal: (rótulo, ícone, ícone selecionado, rota).
DESTINOS = [
    ("Ordens", ft.Icons.ASSIGNMENT_OUTLINED, ft.Icons.ASSIGNMENT, rotas.HOME),
    ("Nova OS", ft.Icons.ADD_CIRCLE_OUTLINE, ft.Icons.ADD_CIRCLE, rotas.OS_NOVA),
]


# Tabela central: nome da rota (ver ui/rotas.py) -> construtor da tela.
TELAS = {
    "login": Login,
    "home": Home,
    "os_nova": CriarOs,
    "os_detalhe": Detalhe,
    "os_editar": EditarOs,
    "os_concluir": ConcluirOs,
}


@dataclass
class Resultado:
    """Resultado de uma chamada de serviço feita por ``App.chamar``."""

    valor: Any = None
    erro: Exception | None = None

    @property
    def ok(self) -> bool:
        return self.erro is None


class App:
    MENSAGEM_GENERICA = MENSAGEM_GENERICA

    def __init__(self, page: ft.Page, config: Config) -> None:
        self.page = page
        self.config = config
        self.sessao = sessao_ui.SessaoUI(timeout_min=config.sessao_timeout_min)
        self._tela: Tela | None = None
        self._rota_mostrada: str | None = None
        self._largo: bool | None = None
        self._mensagem_ao_chegar: str | None = None
        self._rota_a_ignorar: str | None = None

    # --- Inicialização ----------------------------------------------------------------

    async def iniciar(self) -> None:
        page = self.page
        page.title = "Sistema de OS"
        theme.aplicar_tema(page)
        page.padding = 0
        # Textos do próprio Material (contadores, diálogos) em português do Brasil.
        portugues = ft.Locale("pt", "BR")
        page.locale_configuration = ft.LocaleConfiguration(
            supported_locales=[portugues], current_locale=portugues
        )
        page.on_route_change = self._ao_mudar_rota
        page.on_resize = self._ao_redimensionar
        await self._navegar(page.route)

    # --- Navegação --------------------------------------------------------------------

    async def ir(self, rota: str, mensagem: str | None = None, forcar: bool = False) -> None:
        """Navega para a rota (passando pela guarda). ``mensagem`` aparece na chegada.

        Se a tela atual tem alterações não salvas, pede confirmação antes de sair
        (a menos que ``forcar`` seja True).
        """
        if not forcar and self._ha_alteracoes_a_perder(rota):
            self._confirmar_saida(rota, mensagem)
            return
        if forcar:
            self._tela = None  # o usuário já confirmou o descarte
        self._mensagem_ao_chegar = mensagem
        if rotas.normalizar(self.page.route) == rota:
            await self._navegar(rota)  # mesma rota: o evento não dispararia
        else:
            await self.page.push_route(rota)

    def _ha_alteracoes_a_perder(self, destino: str) -> bool:
        return (
            self._tela is not None
            and destino != self._rota_mostrada
            and destino != rotas.LOGIN
            and self._tela.tem_alteracoes()
        )

    def _confirmar_saida(self, destino: str, mensagem: str | None = None) -> None:
        async def descartar() -> None:
            await self.ir(destino, mensagem, forcar=True)

        self.confirmar(
            "Descartar alterações?",
            "As alterações que você fez ainda não foram salvas.",
            "Descartar",
            descartar,
            rotulo_cancelar="Continuar editando",
        )

    def confirmar(
        self,
        titulo: str,
        texto: str,
        rotulo_confirmar: str,
        ao_confirmar,
        rotulo_cancelar: str = "Cancelar",
    ) -> None:
        """Diálogo de confirmação. ``ao_confirmar`` é uma função assíncrona sem argumentos."""

        async def confirmou(_e=None) -> None:
            self.page.pop_dialog()
            await ao_confirmar()

        def cancelou(_e=None) -> None:
            self.page.pop_dialog()

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=theme.COR_CARTAO,
                title=ft.Text(titulo, color=theme.COR_TITULO),
                content=ft.Text(texto, color=theme.COR_SUBTITULO),
                actions=[
                    ft.TextButton(
                        content=rotulo_cancelar,
                        style=theme.estilo_botao_texto(),
                        height=theme.ALVO_TOQUE_MIN,
                        on_click=cancelou,
                    ),
                    ft.TextButton(
                        content=rotulo_confirmar,
                        style=theme.estilo_botao_texto(),
                        height=theme.ALVO_TOQUE_MIN,
                        on_click=confirmou,
                    ),
                ],
            )
        )

    async def voltar(self, _e=None) -> None:
        anterior = rotas.rota_anterior(self._rota_mostrada or rotas.HOME)
        if anterior is not None:
            await self.ir(anterior)

    async def sair(self, _e=None) -> None:
        sessao_ui.encerrar(self.sessao)
        self._tela = None
        await self.ir(rotas.LOGIN, forcar=True)

    async def entrar(self, ator) -> None:
        """Chamado pela tela de login depois de o serviço autenticar o usuário."""
        pendente = self.sessao.rota_pendente
        sessao_ui.iniciar(self.sessao, ator, relogio.agora())
        self.sessao.rota_pendente = None
        await self.ir(rotas.normalizar(pendente) if pendente else rotas.HOME)

    async def _ao_mudar_rota(self, e: ft.RouteChangeEvent) -> None:
        if self._rota_a_ignorar is not None and e.route == self._rota_a_ignorar:
            self._rota_a_ignorar = None  # é só a URL voltando para a tela que continua aberta
            return
        self._rota_a_ignorar = None
        await self._navegar(e.route)

    async def _navegar(self, rota: str | None) -> None:
        """Toda mudança de rota passa aqui, inclusive URL digitada à mão."""
        destino = sessao_ui.aplicar_navegacao(rota, self.sessao, relogio.agora())
        if self.page.route != destino:
            await self.page.push_route(destino)  # dispara de novo _ao_mudar_rota
            return
        if self._ha_alteracoes_a_perder(destino):
            # Saída pelo botão voltar do navegador ou por URL digitada: a URL volta para
            # a tela atual (que continua aberta) e o app pede confirmação.
            self._rota_a_ignorar = self._rota_mostrada
            await self.page.push_route(self._rota_mostrada)
            self._confirmar_saida(destino)
            return
        await self._mostrar(destino)

    async def _mostrar(self, rota: str) -> None:
        nome, params = rotas.resolver(rota) or ("home", {})
        self._rota_mostrada = rota
        self._tela = TELAS[nome](self, **params)
        self._montar()
        mensagem, self._mensagem_ao_chegar = self._mensagem_ao_chegar, None
        if mensagem:
            self.avisar(mensagem)
        await self._tela.carregar()

    # --- Layout -----------------------------------------------------------------------

    def _e_largo(self) -> bool:
        return (self.page.width or 0) >= theme.LARGURA_TRILHO_MIN

    def _indice_destino(self) -> int:
        return 1 if self._rota_mostrada == rotas.OS_NOVA else 0

    async def _ao_escolher_destino(self, e) -> None:
        await self.ir(DESTINOS[int(e.control.selected_index)][3])

    def _montar(self) -> None:
        """Monta a View da rota atual em volta do conteúdo da tela."""
        if self._tela is None or self._rota_mostrada is None:
            return
        page, rota = self.page, self._rota_mostrada
        self._largo = self._e_largo()
        if rota == rotas.LOGIN:
            view = ft.View(
                route=rota,
                padding=0,
                bgcolor=theme.COR_FUNDO_PAGINA,
                scroll=ft.ScrollMode.AUTO,
                controls=[ft.SafeArea(content=self._tela.conteudo)],
            )
        else:
            view = self._view_com_casca(rota)
        page.views.clear()
        page.views.append(view)
        page.update()

    def _view_com_casca(self, rota: str) -> ft.View:
        area = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                cabecalho.saudacao(self.sessao.nome),
                ft.Container(
                    alignment=ft.Alignment.TOP_CENTER,
                    padding=theme.ESPACO_M,
                    content=ft.Container(
                        max_width=theme.LARGURA_MAX_CONTEUDO, content=self._tela.conteudo
                    ),
                ),
            ],
        )
        barra = cabecalho.barra(
            codigo_filial=self.sessao.filial_codigo,
            on_voltar=self.voltar,
            mostrar_voltar=rotas.rota_anterior(rota) is not None,
            itens_menu=[("Sair", ft.Icons.LOGOUT, self.sair)],
            recuo_esquerda=theme.LARGURA_TRILHO + 1 if self._largo else 0,
        )
        barra_inferior = None
        if self._largo:
            trilho = ft.NavigationRail(
                selected_index=self._indice_destino(),
                label_type=ft.NavigationRailLabelType.ALL,
                bgcolor=theme.COR_NAVEGACAO,
                indicator_color=theme.COR_INDICADOR_NAVEGACAO,
                min_width=theme.LARGURA_TRILHO,
                destinations=[
                    ft.NavigationRailDestination(
                        icon=ft.Icon(icone, color=theme.COR_SUBTITULO),
                        selected_icon=ft.Icon(selecionado, color=theme.COR_TITULO),
                        label=ft.Text(rotulo, color=theme.COR_TITULO),
                    )
                    for rotulo, icone, selecionado, _rota in DESTINOS
                ],
                on_change=self._ao_escolher_destino,
            )
            corpo: ft.Control = ft.Row(
                expand=True,
                spacing=0,
                vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                controls=[
                    trilho,
                    ft.VerticalDivider(width=1, thickness=1, color=theme.COR_CONTORNO),
                    area,
                ],
            )
        else:
            corpo = area
            barra_inferior = ft.NavigationBar(
                selected_index=self._indice_destino(),
                bgcolor=theme.COR_NAVEGACAO,
                indicator_color=theme.COR_INDICADOR_NAVEGACAO,
                destinations=[
                    ft.NavigationBarDestination(
                        icon=ft.Icon(icone, color=theme.COR_SUBTITULO),
                        selected_icon=ft.Icon(selecionado, color=theme.COR_TITULO),
                        label=rotulo,
                    )
                    for rotulo, icone, selecionado, _rota in DESTINOS
                ],
                on_change=self._ao_escolher_destino,
            )
        return ft.View(
            route=rota,
            padding=0,
            spacing=0,
            bgcolor=theme.COR_FUNDO_PAGINA,
            navigation_bar=barra_inferior,
            controls=[
                ft.SafeArea(
                    expand=True,
                    content=ft.Column(
                        expand=True,
                        spacing=0,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        controls=[barra, corpo],
                    ),
                )
            ],
        )

    def _ao_redimensionar(self, _e) -> None:
        # Troca entre barra inferior e trilho lateral ao cruzar os 600 px.
        if self._largo is not None and self._e_largo() != self._largo:
            self._montar()

    # --- Mensagens --------------------------------------------------------------------

    def avisar(self, mensagem: str) -> None:
        self.page.show_dialog(
            ft.SnackBar(
                content=ft.Text(mensagem, color=theme.COR_SOBRE_CABECALHO),
                bgcolor=theme.COR_CABECALHO,
            )
        )

    # --- Chamada de serviços ----------------------------------------------------------

    async def chamar(
        self,
        funcao,
        *args,
        exige_sessao: bool = True,
        erros_tratados: tuple[type[Exception], ...] = (),
        campos: dict[str, ft.Control] | None = None,
    ) -> Resultado:
        """Executa uma função de serviço (bloqueante) fora do laço de eventos.

        - ErroValidacao: a mensagem aparece no campo correspondente de ``campos`` ou,
          se não houver, em um aviso.
        - ErroAutenticacao: a sessão é encerrada e o app volta para /login.
        - Erros em ``erros_tratados``: devolvidos para a tela decidir o que mostrar.
        - Qualquer outro erro: mensagem genérica para o usuário e traceback no log.
        O texto de uma exceção nunca é mostrado ao usuário (exceto ErroValidacao).
        """
        agora = relogio.agora()
        if exige_sessao:
            if not sessao_ui.autenticada(self.sessao, agora):
                await self._navegar(self.page.route)  # a guarda leva para /login
                return Resultado(erro=ErroAutenticacao())
            sessao_ui.registrar_atividade(self.sessao, agora)
        try:
            return Resultado(valor=await asyncio.to_thread(funcao, *args))
        except erros_tratados as exc:
            return Resultado(erro=exc)
        except ErroValidacao as exc:
            campo = (campos or {}).get(exc.campo)
            if campo is not None:
                campo.error = exc.mensagem
                campo.update()
            else:
                self.avisar(exc.mensagem)
            return Resultado(erro=exc)
        except ErroAutenticacao as exc:
            sessao_ui.encerrar(self.sessao)
            await self.ir(rotas.LOGIN)
            return Resultado(erro=exc)
        except Exception as exc:  # noqa: BLE001 - nada de texto de exceção para o usuário
            logger.exception("Erro inesperado ao chamar %s.", getattr(funcao, "__name__", "?"))
            self.avisar(MENSAGEM_GENERICA)
            return Resultado(erro=exc)
