"""Nova Solicitação (/solicitacao/nova) e Editar Solicitação (/os/{id}/solicitacao).

Usam só os serviços de solicitação; o modelo de leitura que voltar (reduzido para o papel
usuario) é o único dado mostrado.
"""

from __future__ import annotations

import flet as ft

from osapp.services import ordens
from osapp.services.erros import ErroConflito, ErroNaoEncontrado, ErroPermissao
from osapp.ui import rotas, secoes, theme
from osapp.ui import urgencia as urgencia_ui
from osapp.ui.components import basicos
from osapp.ui.components.opcoes import OpcaoGrupo
from osapp.ui.components.secao import SecaoCard, secao, status_pill
from osapp.ui.views.base import Tela
from osapp.ui.views.detalhe import MENSAGEM_CONFLITO

TITULO_NOVA = "Nova Solicitação"
TITULO_EDITAR = "Editar solicitação"
ROTULO_ENVIAR = "Enviar solicitação"
ROTULO_SALVAR = "Salvar alterações"
MSG_ESCOLHA_URGENCIA = "Escolha a urgência."


def grupo_urgencia(valor: str | None = None, ao_mudar=None) -> OpcaoGrupo:
    """Urgência como cartões de opção (ponto colorido, rótulo e significado)."""
    return OpcaoGrupo(urgencia_ui.opcoes(theme.COR_PONTO_URGENCIA), valor, ao_mudar)


def tom_urgencia(nivel: str | None) -> str:
    return nivel or "neutro"


DICA_ESCOPO_TI = "Problemas de computador, rede ou sistemas: abrir chamado com a TI."


class _FormularioSolicitacao(Tela):
    banner = None
    titulo_da_tela = ""
    rotulo_do_botao = ""
    dica_titulo: str | None = None

    def __init__(self, app) -> None:
        self.app = app
        self.aviso = ft.Text("", color=theme.COR_ERRO, size=theme.FONTE_SUBTITULO, visible=False)
        self.botao = basicos.botao_primario(self.rotulo_do_botao, ft.Icons.SEND, self._enviar)
        self.conteudo = basicos.coluna([basicos.carregando()])
        self._inicial: tuple | None = None

    def _montar(self, titulo="", descricao="", urgencia=None, filial="") -> None:
        limpar = self._limpar_erro
        extra = {"helper": self.dica_titulo, "helper_max_lines": 2} if self.dica_titulo else {}
        self.titulo = basicos.campo_texto(
            "Título", value=titulo, max_length=ordens.TITULO_MAX, on_change=limpar, **extra
        )
        self.descricao = basicos.campo_texto(
            "Descrição",
            value=descricao,
            multiline=True,
            min_lines=3,
            max_lines=8,
            max_length=ordens.DESCRICAO_MAX,
            on_change=limpar,
        )
        self.urgencia = grupo_urgencia(urgencia, self._ao_mudar_urgencia)
        self.campos = {
            "titulo": self.titulo,
            "descricao": self.descricao,
            "urgencia": self.urgencia,
        }
        lista = secoes.secoes(self.app.sessao.papel, solicitacao=True)
        self.secao_urgencia = SecaoCard(
            secoes.numero(lista, secoes.URGENCIA),
            ft.Icons.PRIORITY_HIGH,
            secoes.TITULOS[secoes.URGENCIA],
            [self.urgencia.controle],
            obrigatoria=True,
            pill=status_pill(urgencia_ui.pill(urgencia), tom_urgencia(urgencia)),
        )
        self.conteudo.controls = [
            basicos.titulo(self.titulo_da_tela, theme.FONTE_SAUDACAO)
            if self.banner is None
            else ft.Container(),
            secao(
                secoes.numero(lista, secoes.SOLICITACAO),
                ft.Icons.DESCRIPTION_OUTLINED,
                secoes.TITULOS[secoes.SOLICITACAO],
                [basicos.rotulo_valor("Filial", filial), self.titulo, self.descricao],
                obrigatoria=True,
            ),
            self.secao_urgencia.controle,
            self.aviso,
            self.botao,
        ]
        self._inicial = self._digitado()

    def _ao_mudar_urgencia(self) -> None:
        v = self.urgencia.valor
        self.secao_urgencia.definir_pill(status_pill(urgencia_ui.pill(v), tom_urgencia(v)))

    def _digitado(self) -> tuple:
        return (self.titulo.value or "", self.descricao.value or "", self.urgencia.valor)

    def tem_alteracoes(self) -> bool:
        return self._inicial is not None and self._digitado() != self._inicial

    def _limpar_erro(self, e) -> None:
        if e.control.error:
            e.control.error = None
            e.control.update()

    def _mensagem(self, texto: str, rota: str, rotulo: str) -> None:
        async def voltar(_e=None) -> None:
            await self.app.ir(rota)

        self.conteudo.controls = [
            basicos.mensagem_central(texto),
            basicos.botao_secundario(rotulo, ft.Icons.ARROW_BACK, voltar),
        ]

    def _atualizar(self) -> None:
        try:
            self.conteudo.update()
        except RuntimeError:
            pass  # a tela já foi trocada

    async def _enviar(self, _e=None) -> None:
        if self.botao.disabled or self._inicial is None:
            return
        self.aviso.visible = False
        if self.urgencia.valor is None:  # conveniência; o serviço também recusa
            self.urgencia.marcar_erro(MSG_ESCOLHA_URGENCIA)
            self._atualizar()
            return
        self.botao.disabled = True
        self._atualizar()
        try:
            await self._gravar()
        finally:
            self.botao.disabled = False
            self._atualizar()

    async def _gravar(self) -> None:
        raise NotImplementedError


class NovaSolicitacao(_FormularioSolicitacao):
    banner = (ft.Icons.ADD_COMMENT, TITULO_NOVA)
    titulo_da_tela = TITULO_NOVA
    rotulo_do_botao = ROTULO_ENVIAR
    dica_titulo = DICA_ESCOPO_TI  # prompt 41

    def __init__(self, app, **_params) -> None:
        super().__init__(app)

    async def carregar(self) -> None:
        sessao = self.app.sessao
        self._montar(filial=sessao.filial_codigo)  # travada na filial do usuário
        self._atualizar()

    async def _gravar(self) -> None:
        resultado = await self.app.chamar(
            ordens.criar_solicitacao,
            self.app.sessao.ator_id,
            (self.titulo.value or "").strip(),
            (self.descricao.value or "").strip(),
            self.urgencia.valor,
            campos=self.campos,
        )
        if resultado.ok:
            self._inicial = self._digitado()  # nada a perder ao sair
            await self.app.atualizar_contadores()
            await self.app.ir(
                rotas.rota_os(resultado.valor.id),
                mensagem=f"Solicitação {resultado.valor.numero} enviada.",
            )


class EditarSolicitacao(_FormularioSolicitacao):
    titulo_da_tela = TITULO_EDITAR
    rotulo_do_botao = ROTULO_SALVAR

    def __init__(self, app, os_id: int, **_params) -> None:
        super().__init__(app)
        self.os_id = os_id
        self.os = None

    async def carregar(self) -> None:
        resultado = await self.app.chamar(
            ordens.obter_os,
            self.app.sessao.ator_id,
            self.os_id,
            erros_tratados=(ErroNaoEncontrado,),
        )
        destino = rotas.rota_os(self.os_id)
        if isinstance(resultado.erro, ErroNaoEncontrado):
            self._mensagem("Ordem de Serviço não encontrada.", rotas.HOME, "Voltar para a lista")
        elif not resultado.ok:
            self._mensagem("Não foi possível abrir a tela.", rotas.HOME, "Voltar para a lista")
        else:
            d = resultado.valor
            pode = (
                d.acoes.pode_editar
                if isinstance(d, ordens.OsVisaoSolicitante)
                else d.acoes.pode_editar_solicitacao
            )
            if not pode:  # a rota foi aberta sem permissão: o serviço diz que não pode
                self._mensagem(
                    self.app.MENSAGEM_GENERICA, destino, "Voltar para a Ordem de Serviço"
                )
            else:
                self.os = d
                self._montar(d.titulo, d.descricao, d.urgencia, d.filial_codigo)
        self._atualizar()

    async def _gravar(self) -> None:
        titulo, descricao, urgencia = self._digitado()
        alteracoes = {
            campo: valor
            for campo, valor, antes in (
                ("titulo", titulo.strip(), self.os.titulo),
                ("descricao", descricao.strip(), self.os.descricao),
                ("urgencia", urgencia, self.os.urgencia),
            )
            if valor != antes
        }
        destino = rotas.rota_os(self.os_id)
        if not alteracoes:
            self._inicial = self._digitado()
            await self.app.ir(destino, mensagem="Nenhuma alteração para salvar.")
            return
        resultado = await self.app.chamar(
            ordens.editar_solicitacao,
            self.app.sessao.ator_id,
            self.os_id,
            self.os.versao,
            alteracoes,
            campos=self.campos,
            erros_tratados=(ErroConflito, ErroPermissao, ErroNaoEncontrado),
        )
        if resultado.ok:
            self._inicial = self._digitado()
            await self.app.ir(destino, mensagem="Solicitação alterada.")
        elif isinstance(resultado.erro, ErroConflito):
            self.aviso.value = MENSAGEM_CONFLITO
            self.aviso.visible = True
            self.app.avisar(MENSAGEM_CONFLITO)
        elif isinstance(resultado.erro, ErroPermissao | ErroNaoEncontrado):
            self.app.avisar(self.app.MENSAGEM_GENERICA)
