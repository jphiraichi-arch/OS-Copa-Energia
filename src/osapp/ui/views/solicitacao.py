"""Nova Solicitação (/solicitacao/nova) e Editar Solicitação (/os/{id}/solicitacao).

Usam só os serviços de solicitação; o modelo de leitura que voltar (reduzido para o papel
usuario) é o único dado mostrado.
"""

from __future__ import annotations

import flet as ft

from osapp.services import ordens
from osapp.services.erros import ErroConflito, ErroNaoEncontrado, ErroPermissao
from osapp.ui import rotas, rotulos, theme
from osapp.ui.components import basicos
from osapp.ui.views.base import Tela
from osapp.ui.views.detalhe import MENSAGEM_CONFLITO

TITULO_NOVA = "Nova Solicitação"
TITULO_EDITAR = "Editar solicitação"
ROTULO_ENVIAR = "Enviar solicitação"
ROTULO_SALVAR = "Salvar alterações"
ROTULO_URGENCIA = "Urgência"
MSG_ESCOLHA_URGENCIA = "Escolha a urgência."
ALTURA_OPCAO = 56  # acima do alvo mínimo de 48 px


class SeletorUrgencia:
    """Quatro opções grandes; uma é obrigatória. A palavra aparece sempre (não só cor)."""

    def __init__(self, valor: str | None = None, ao_mudar=None) -> None:
        self.valor = valor
        self._ao_mudar = ao_mudar
        self.erro = ft.Text("", color=theme.COR_ERRO, size=theme.FONTE_PEQUENA, visible=False)
        self.opcoes = ft.ResponsiveRow(spacing=theme.ESPACO_P, run_spacing=theme.ESPACO_P)
        self.controle = ft.Column(
            [
                ft.Text(ROTULO_URGENCIA, color=theme.COR_SUBTITULO, size=theme.FONTE_SUBTITULO),
                self.opcoes,
                self.erro,
            ],
            spacing=theme.ESPACO_P,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self._montar()

    def _montar(self) -> None:
        self.opcoes.controls = [self._opcao(nivel) for nivel in ordens.NIVEIS]

    def _opcao(self, nivel: str) -> ft.Control:
        escolhida = nivel == self.valor
        fundo, cor = theme.cores_nivel(nivel)
        icone = ft.Icons.CHECK_CIRCLE if escolhida else ft.Icons.RADIO_BUTTON_UNCHECKED
        return ft.Container(
            col={"xs": 6, "sm": 3},
            height=ALTURA_OPCAO,
            bgcolor=fundo if escolhida else theme.COR_CAMPO_FUNDO,
            border=ft.Border.all(2 if escolhida else 1, cor if escolhida else theme.COR_CONTORNO),
            border_radius=theme.RAIO_BOTAO,
            ink=True,
            on_click=lambda _e, n=nivel: self._escolher(n),
            alignment=ft.Alignment.CENTER,
            content=ft.Row(
                [
                    ft.Icon(icone, color=cor if escolhida else theme.COR_SUBTITULO, size=20),
                    ft.Text(
                        rotulos.nivel(nivel),
                        color=cor if escolhida else theme.COR_TITULO,
                        size=theme.FONTE_CORPO,
                        weight=ft.FontWeight.BOLD if escolhida else ft.FontWeight.NORMAL,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=6,
            ),
        )

    def _escolher(self, nivel: str) -> None:
        self.valor = nivel
        self.marcar_erro(None)
        self._montar()
        self.controle.update()
        if self._ao_mudar:
            self._ao_mudar()

    def marcar_erro(self, mensagem: str | None) -> None:
        self.erro.value = mensagem or ""
        self.erro.visible = bool(mensagem)

    # Para App.chamar marcar o ErroValidacao do serviço como num campo.
    @property
    def error(self) -> str | None:
        return self.erro.value or None

    @error.setter
    def error(self, mensagem: str | None) -> None:
        self.marcar_erro(mensagem)

    def update(self) -> None:
        self.controle.update()


class _FormularioSolicitacao(Tela):
    titulo_da_tela = ""
    rotulo_do_botao = ""

    def __init__(self, app) -> None:
        self.app = app
        self.aviso = ft.Text("", color=theme.COR_ERRO, size=theme.FONTE_SUBTITULO, visible=False)
        self.botao = basicos.botao_primario(self.rotulo_do_botao, ft.Icons.SEND, self._enviar)
        self.conteudo = basicos.coluna([basicos.carregando()])
        self._inicial: tuple | None = None

    def _montar(self, titulo="", descricao="", urgencia=None, filial="") -> None:
        limpar = self._limpar_erro
        self.titulo = basicos.campo_texto(
            "Título", value=titulo, max_length=ordens.TITULO_MAX, on_change=limpar
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
        self.urgencia = SeletorUrgencia(urgencia)
        self.campos = {
            "titulo": self.titulo,
            "descricao": self.descricao,
            "urgencia": self.urgencia,
        }
        self.conteudo.controls = [
            basicos.cartao(
                basicos.coluna(
                    [
                        basicos.titulo(self.titulo_da_tela),
                        basicos.rotulo_valor("Filial", filial),
                        self.titulo,
                        self.descricao,
                        self.urgencia.controle,
                        self.aviso,
                    ]
                )
            ),
            self.botao,
        ]
        self._inicial = self._digitado()

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
    titulo_da_tela = TITULO_NOVA
    rotulo_do_botao = ROTULO_ENVIAR

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
