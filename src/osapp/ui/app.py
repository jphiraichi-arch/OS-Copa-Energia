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

from osapp import guia
from osapp.config import Config
from osapp.services import alertas, ordens, relogio, sessoes_lembradas
from osapp.services.erros import ErroAutenticacao, ErroValidacao
from osapp.ui import navegacao, rotas, textos, theme
from osapp.ui import sessao as sessao_ui
from osapp.ui.components import basicos, cabecalho
from osapp.ui.components.banner import banner
from osapp.ui.components.barra_inferior import BarraInferior
from osapp.ui.views.base import Tela
from osapp.ui.views.concluir import ConcluirOs
from osapp.ui.views.configuracoes import Configuracoes
from osapp.ui.views.detalhe import Detalhe
from osapp.ui.views.especialidades import Especialidades, MotivosCancelamento
from osapp.ui.views.home import Home
from osapp.ui.views.lixeira import Lixeira, LixeiraDetalhe
from osapp.ui.views.login import Login
from osapp.ui.views.os_formulario import AssumirOs, CriarOs, EditarOs
from osapp.ui.views.perfil import AlterarSenha, Perfil
from osapp.ui.views.relatorio_tempos import RelatorioTempos
from osapp.ui.views.relatorios import Relatorios
from osapp.ui.views.senha import TrocarSenha
from osapp.ui.views.sla import Sla
from osapp.ui.views.solicitacao import EditarSolicitacao, NovaSolicitacao
from osapp.ui.views.usuarios import FormularioUsuario, ListaUsuarios

logger = logging.getLogger(__name__)

MENSAGEM_GENERICA = "Não foi possível concluir a operação. Tente novamente."

# Ícones de cada destino da barra inferior (os destinos por papel vêm de ui/navegacao.py).
ICONES = {
    "nova_os": (ft.Icons.ADD_CIRCLE_OUTLINE, ft.Icons.ADD_CIRCLE),
    "ordens": (ft.Icons.ASSIGNMENT_OUTLINED, ft.Icons.ASSIGNMENT),
    "relatorios": (ft.Icons.INSERT_CHART_OUTLINED, ft.Icons.INSERT_CHART),
    "perfil": (ft.Icons.PERSON_OUTLINE, ft.Icons.PERSON),
}


# Tabela central: nome da rota (ver ui/rotas.py) -> construtor da tela.
TELAS = {
    "login": Login,
    "home": Home,
    "perfil": Perfil,
    "alterar_senha": AlterarSenha,
    "especialidades": Especialidades,
    "sla": Sla,
    "motivos_cancelamento": MotivosCancelamento,
    "lixeira": Lixeira,
    "lixeira_detalhe": LixeiraDetalhe,
    "configuracoes": Configuracoes,
    "trocar_senha": TrocarSenha,
    "usuarios": ListaUsuarios,
    "usuario_novo": FormularioUsuario,
    "usuario": FormularioUsuario,
    "relatorios": RelatorioTempos,
    "relatorios_mensal": Relatorios,
    "os_nova": CriarOs,
    "os_detalhe": Detalhe,
    "os_editar": EditarOs,
    "os_assumir": AssumirOs,
    "os_solicitacao": EditarSolicitacao,
    "solicitacao_nova": NovaSolicitacao,
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
        # Faixa e selo de 'Ordens' (services.ordens.contadores).
        self.contadores: ordens.Contadores | None = None
        self.filtro_filial: int | None = None  # filial escolhida no filtro (administrador)
        # Prompt 35: família do token 'Lembrar de mim' deste navegador (None sem token) e
        # se já se tentou entrar com o token desde a última entrada.
        self.familia_lembrada: str | None = None
        self._token_tentado = False
        self._lugar_banner = ft.Container()
        self._barra_inferior: BarraInferior | None = None

    # --- Inicialização ----------------------------------------------------------------

    async def iniciar(self) -> None:
        page = self.page
        page.title = textos.TITULO_DO_APP
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
        """'Sair': revoga o 'Lembrar de mim' deste aparelho e apaga o token guardado."""
        if self.familia_lembrada is not None and self.sessao.ator_id is not None:
            await self.chamar(
                sessoes_lembradas.sair_deste_aparelho, self.sessao.ator_id, self.familia_lembrada
            )
        await self.esquecer_token()
        sessao_ui.encerrar(self.sessao)
        self._tela = None
        self._token_tentado = True  # sem token: não tentar de novo nesta visita
        await self.ir(rotas.LOGIN, forcar=True)

    # --- 'Lembrar de mim' (prompt 35) -----------------------------------------------------

    async def guardar_token(self, emitido) -> None:
        self.familia_lembrada = emitido.familia
        try:
            await ft.SharedPreferences().set(sessoes_lembradas.CHAVE_NAVEGADOR, emitido.token)
        except Exception:  # noqa: BLE001 - sem armazenamento: só não lembra
            logger.warning("Não foi possível guardar o token 'lembrar de mim' no navegador.")

    async def esquecer_token(self) -> None:
        self.familia_lembrada = None
        try:
            await ft.SharedPreferences().remove(sessoes_lembradas.CHAVE_NAVEGADOR)
        except Exception:  # noqa: BLE001
            logger.warning("Não foi possível apagar o token 'lembrar de mim' do navegador.")

    async def _entrar_com_token(self) -> bool:
        """Sem sessão (ou expirada): tenta o token guardado. Recusa: apaga o token e
        segue para o login normal (todas as recusas são iguais para o usuário)."""
        self._token_tentado = True
        try:
            token = await ft.SharedPreferences().get(sessoes_lembradas.CHAVE_NAVEGADOR)
        except Exception:  # noqa: BLE001
            return False
        if not isinstance(token, str) or not token:
            return False
        resultado = await self.chamar(
            sessoes_lembradas.entrar_com_token,
            token,
            self.page.client_ip,
            exige_sessao=False,
            erros_tratados=(ErroAutenticacao,),
        )
        if not resultado.ok:
            await self.esquecer_token()
            return False
        entrada = resultado.valor
        await self.guardar_token(entrada.emitido)
        sessao_ui.iniciar(self.sessao, entrada.ator, relogio.agora(), "")
        self.contadores = None
        self.filtro_filial = entrada.ator.filial_id if self.sessao.e_admin else None
        self._token_tentado = False  # numa nova expiração, tenta de novo (até os 7 dias)
        return True

    async def atualizar_contadores(self) -> None:
        """Busca os números da faixa e do selo; chamado no login, em 'Atualizar' e
        depois de cada mudança de status feita nesta sessão."""
        if self.sessao.ator_id is None:
            return
        resultado = await self.chamar(ordens.contadores, self.sessao.ator_id, self.filtro_filial)
        if not resultado.ok:
            return
        self.contadores = resultado.valor
        self._desenhar_banner()
        if self._barra_inferior is not None:
            self._barra_inferior.definir_selo(self._indice_ordens(), self._texto_selo_ordens())

    async def entrar(self, ator, login: str = "", lembrar: bool = False) -> None:
        """Chamado pela tela de login depois de o serviço autenticar o usuário.
        ``lembrar``: a caixa 'Lembrar de mim por 7 dias' estava marcada."""
        pendente = self.sessao.rota_pendente
        sessao_ui.iniciar(self.sessao, ator, relogio.agora(), login)
        self._token_tentado = False
        if lembrar:
            emitido = await self.chamar(
                sessoes_lembradas.lembrar, ator.usuario_id, self.page.client_user_agent
            )
            if emitido.ok:
                await self.guardar_token(emitido.valor)
        self.sessao.rota_pendente = None
        self.contadores = None
        self.filtro_filial = ator.filial_id if self.sessao.e_admin else None
        await self.ir(rotas.normalizar(pendente) if pendente else rotas.HOME)

    async def _ao_mudar_rota(self, e: ft.RouteChangeEvent) -> None:
        if self._rota_a_ignorar is not None and e.route == self._rota_a_ignorar:
            self._rota_a_ignorar = None  # é só a URL voltando para a tela que continua aberta
            return
        self._rota_a_ignorar = None
        await self._navegar(e.route)

    async def _navegar(self, rota: str | None) -> None:
        """Toda mudança de rota passa aqui, inclusive URL digitada à mão."""
        if sessao_ui.deve_tentar_token(self.sessao, relogio.agora(), self._token_tentado):
            await self._entrar_com_token()
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
        if self.contadores is None and rota not in (rotas.LOGIN, rotas.TROCAR_SENHA):
            await self.atualizar_contadores()  # antes de montar: faixa e selo já prontos
        self._montar()
        mensagem, self._mensagem_ao_chegar = self._mensagem_ao_chegar, None
        if mensagem:
            self.avisar(mensagem)
        await self._tela.carregar()

    # --- Layout -----------------------------------------------------------------------

    def _e_largo(self) -> bool:
        """Tela larga (tablet ou PC): a partir de theme.LARGURA_CELULAR_MAX."""
        return (self.page.width or 0) >= theme.LARGURA_CELULAR_MAX

    def _destinos(self):
        return navegacao.destinos(self.sessao.papel)

    def _ao_escolher_destino(self, indice: int) -> None:
        self.page.run_task(self.ir, self._destinos()[indice].rota)

    def _texto_selo_ordens(self) -> str | None:
        """Selo de 'Ordens': quantas ordens com status Aberta (prompt 41)."""
        abertas = self.contadores.abertas if self.contadores else 0
        return str(abertas) if abertas else None

    def _indice_ordens(self) -> int:
        return next((i for i, d in enumerate(self._destinos()) if d.chave == "ordens"), -1)

    def _destinos_da_barra(self) -> list[tuple[str, ft.IconData, ft.IconData]]:
        return [(d.rotulo, ICONES[d.chave][0], ICONES[d.chave][1]) for d in self._destinos()]

    def _desenhar_banner(self) -> None:
        """Faixa da tela atual (se ela tiver uma), com a filial e os contadores."""
        tela = self._tela
        dados = getattr(tela, "banner", None) if tela is not None else None
        if not dados:
            self._lugar_banner.content = None
        else:
            icone, titulo = dados
            c = self.contadores
            indicadores = (
                [
                    (textos.BANNER_ABERTAS, str(c.abertas)),
                    (textos.BANNER_EM_EXECUCAO, str(c.em_execucao)),
                ]
                if c
                else []
            )
            self._lugar_banner.content = banner(
                icone,
                titulo,
                c.filial_rotulo if c else self.sessao.filial_codigo,
                indicadores,
                celular=not self._e_largo(),
            )
        try:
            self._lugar_banner.update()
        except RuntimeError:
            pass  # ainda não está na página

    def _montar(self) -> None:
        """Monta a View da rota atual em volta do conteúdo da tela."""
        if self._tela is None or self._rota_mostrada is None:
            return
        page, rota = self.page, self._rota_mostrada
        self._largo = self._e_largo()
        if rota in (rotas.LOGIN, rotas.TROCAR_SENHA):  # sem navegação
            self._barra_inferior = None
            ajuda = self._botao_ajuda(rota, theme.COR_PRIMARIO)
            conteudo = self._tela.conteudo
            if ajuda is not None:
                conteudo = ft.Column(
                    [ft.Row([ajuda], alignment=ft.MainAxisAlignment.END), conteudo],
                    spacing=0,
                )
            view = ft.View(
                route=rota,
                padding=0,
                bgcolor=theme.COR_FUNDO_PAGINA,
                scroll=ft.ScrollMode.AUTO,
                controls=[ft.SafeArea(content=conteudo)],
            )
        else:
            view = self._view_com_casca(rota)
        page.views.clear()
        page.views.append(view)
        page.update()

    def _view_com_casca(self, rota: str) -> ft.View:
        """Barra superior fina (logo e filial), conteúdo centralizado com no máximo
        theme.LARGURA_MAX_CONTEUDO e a barra inferior em todos os tamanhos de tela."""
        self._lugar_banner = ft.Container()
        self._desenhar_banner()
        area = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            controls=[
                ft.Container(
                    alignment=ft.Alignment.TOP_CENTER,
                    padding=theme.ESPACO_M,
                    content=ft.Container(
                        max_width=theme.LARGURA_MAX_CONTEUDO,
                        content=ft.Column(
                            [self._lugar_banner, self._tela.conteudo],
                            spacing=theme.ESPACO_M,
                            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        ),
                    ),
                ),
            ],
        )
        barra = cabecalho.barra(
            codigo_filial=self.sessao.filial_codigo,
            on_voltar=self.voltar,
            mostrar_voltar=rotas.rota_anterior(rota) is not None,
            ajuda=self._botao_ajuda(rota),
        )
        ativo = navegacao.destino_ativo(self.sessao.papel, rota)
        selo = self._texto_selo_ordens()
        self._barra_inferior = BarraInferior(
            self._destinos_da_barra(),
            ativo,
            self._ao_escolher_destino,
            self._e_largo(),
            {self._indice_ordens(): selo} if selo else None,
        )
        return ft.View(
            route=rota,
            padding=0,
            spacing=0,
            bgcolor=theme.COR_FUNDO_PAGINA,
            controls=[
                ft.SafeArea(
                    expand=True,
                    content=ft.Column(
                        expand=True,
                        spacing=0,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                        # A barra inferior vem depois da área rolável (que tem expand):
                        # o conteúdo termina acima dela, nunca por baixo (prompt 41).
                        controls=[barra, area, self._barra_inferior.controle],
                    ),
                )
            ],
        )

    # --- Guia rápido (prompt 39) ---------------------------------------------------------

    def _botao_ajuda(self, rota: str, cor=None) -> ft.Control | None:
        """O '?' só aparece se o guia tem texto da tela para o papel (ou 'todos')."""
        resolvida = rotas.resolver(rota)
        entrada = guia.entrada(resolvida[0], self.sessao.papel) if resolvida else None
        if entrada is None:
            return None
        return cabecalho.botao_ajuda(lambda _e: self.mostrar_ajuda(entrada), cor)

    def mostrar_ajuda(self, entrada) -> None:
        """Folha de baixo no celular, diálogo na tela larga. Os links do texto aparecem,
        mas nunca são abertos sozinhos (sem auto_follow_links nem on_tap_link)."""
        texto = ft.Markdown(
            entrada.texto,
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.COMMON_MARK,
            auto_follow_links=False,
        )

        def fechar(_e=None) -> None:
            self.page.pop_dialog()

        botao_fechar = ft.TextButton(
            content="Fechar",
            style=theme.estilo_botao_texto(),
            height=theme.ALVO_TOQUE_MIN,
            on_click=fechar,
        )
        if self._e_largo():
            self.page.show_dialog(
                ft.AlertDialog(
                    bgcolor=theme.COR_CARTAO,
                    title=ft.Text(entrada.titulo, color=theme.COR_TITULO),
                    content=ft.Container(width=theme.LARGURA_MAX_LOGIN, content=texto),
                    actions=[botao_fechar],
                )
            )
        else:
            self.page.show_dialog(
                ft.BottomSheet(
                    bgcolor=theme.COR_CARTAO,
                    show_drag_handle=True,
                    scrollable=True,
                    content=ft.Container(
                        padding=theme.ESPACO_M,
                        content=ft.Column(
                            [basicos.titulo(entrada.titulo), texto, botao_fechar],
                            tight=True,
                            spacing=theme.ESPACO_P,
                        ),
                    ),
                )
            )

    def _ao_redimensionar(self, _e) -> None:
        # Faixa e grades mudam entre celular e tela larga ao cruzar theme.LARGURA_CELULAR_MAX.
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
        resolvida = rotas.resolver(self._rota_mostrada)
        alertas.ROTA.set(resolvida[0] if resolvida else None)  # prompt 33: rota no alerta
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
