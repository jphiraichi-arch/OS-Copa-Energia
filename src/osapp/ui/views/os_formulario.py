"""Telas Criar Ordem de Serviço (/os/nova) e Alterar Ordem de Serviço (/os/{id}/editar)."""

from __future__ import annotations

from functools import partial

import flet as ft

from osapp import formatacao
from osapp.services import custos, ordens
from osapp.services.erros import ErroConflito, ErroNaoEncontrado, ErroPermissao, ErroValidacao
from osapp.ui import formularios, rotas, rotulos, secoes, theme
from osapp.ui import urgencia as urgencia_ui
from osapp.ui.components import basicos
from osapp.ui.components.editor_itens import ADICIONAR, EDITAR, EditorItens
from osapp.ui.components.formulario_os import FormularioOs
from osapp.ui.components.opcoes import opcao_card
from osapp.ui.components.secao import SecaoCard, secao, status_pill
from osapp.ui.views.base import Tela
from osapp.ui.views.detalhe import MENSAGEM_CONFLITO

TITULO_PREVISTOS = "Custos previstos"
TITULO_REALIZADOS = "Custos realizados"


class AlvoDeErro:
    """Faz o editor de itens receber, como um campo, a mensagem de ErroValidacao da lista."""

    def __init__(self, editor: EditorItens) -> None:
        self._editor = editor

    @property
    def error(self) -> str | None:
        return self._editor.erro.value or None

    @error.setter
    def error(self, mensagem: str | None) -> None:
        self._editor.erro.value = mensagem or ""
        self._editor.erro.visible = bool(mensagem)

    def update(self) -> None:
        self._editor.marcar_erro(self._editor.erro.value or None)


class _TelaDeFormulario(Tela):
    banner = None
    titulo_da_tela = ""
    rotulo_do_botao = ""

    def __init__(self, app) -> None:
        self.app = app
        self.formulario: FormularioOs | None = None
        self.editores: list[EditorItens] = []
        self.aviso = ft.Text("", color=theme.COR_ERRO, size=theme.FONTE_SUBTITULO, visible=False)
        self.botao = basicos.botao_primario(self.rotulo_do_botao, ft.Icons.SAVE, self._salvar)
        self.conteudo = basicos.coluna([basicos.carregando()])

    def tem_alteracoes(self) -> bool:
        return self.formulario is not None and self.formulario.tem_alteracoes()

    def _lista_de_secoes(self) -> tuple[str, ...]:
        """Seções pelo papel e pela Ordem de Serviço carregada (ui/secoes.py)."""
        os_ = getattr(self, "os", None)
        return secoes.secoes(
            self.app.sessao.papel,
            os_.status if os_ else None,
            solicitacao=bool(os_ and os_.origem == ordens.ORIGEM_SOLICITACAO),
        )

    def _mostrar_formulario(self) -> None:
        """Um SecaoCard numerado por seção: 1. SOLICITAÇÃO, 2. URGÊNCIA (só leitura: é do
        solicitante), PLANEJAMENTO, ITENS DE CUSTO e, para o administrador numa Ordem de
        Serviço concluída, CONCLUSÃO."""
        f = self.formulario
        lista = tuple(
            s
            for s in self._lista_de_secoes()
            if s != secoes.CONCLUSAO or secoes.CONCLUSAO in f.partes
        )
        os_ = getattr(self, "os", None)
        cartoes: list[ft.Control] = []
        self.secao_planejamento = self.secao_itens = None
        for chave in lista:
            n, titulo = secoes.numero(lista, chave), secoes.TITULOS[chave]
            if chave == secoes.SOLICITACAO:
                cartoes.append(
                    secao(n, ft.Icons.DESCRIPTION_OUTLINED, titulo, f.partes[chave], True)
                )
            elif chave == secoes.URGENCIA:
                nivel = os_.urgencia if os_ else None
                cartoes.append(
                    secao(
                        n,
                        ft.Icons.PRIORITY_HIGH,
                        titulo,
                        [
                            basicos.subtitulo("Informada pelo solicitante."),
                            opcao_card(
                                theme.cor_ponto_urgencia(nivel),
                                rotulos.nivel(nivel),
                                urgencia_ui.SIGNIFICADO.get(nivel, ""),
                                True,
                            ),
                        ],
                        pill=status_pill(urgencia_ui.pill(nivel), nivel or "neutro"),
                    )
                )
            elif chave == secoes.PLANEJAMENTO:
                self.secao_planejamento = SecaoCard(
                    n,
                    ft.Icons.EVENT_NOTE,
                    titulo,
                    f.partes[chave],
                    pill=status_pill(f.resumo_planejamento(), "info"),
                )
                f.observar_planejamento(self._atualizar_pill_planejamento)
                cartoes.append(self.secao_planejamento.controle)
            elif chave == secoes.ITENS:
                self.secao_itens = SecaoCard(
                    n,
                    ft.Icons.RECEIPT_LONG,
                    titulo,
                    [editor.controle for editor in self.editores],
                    pill=status_pill(self._resumo_itens(), "info"),
                )
                for editor in self.editores:
                    editor.observar(self._atualizar_pill_itens)
                cartoes.append(self.secao_itens.controle)
            elif chave == secoes.CONCLUSAO:
                cartoes.append(secao(n, ft.Icons.TASK_ALT, titulo, f.partes[chave]))
        self.conteudo.controls = [
            *([] if self.banner else [basicos.titulo(self.titulo_da_tela, theme.FONTE_SAUDACAO)]),
            *cartoes,
            self.aviso,
            self.botao,
        ]

    def _resumo_itens(self) -> str:
        """'PREVISTO: R$ 1.250,00' (subtotal ao vivo da fase prevista)."""
        previsto = next((e for e in self.editores if e.fase == custos.FASE_PREVISTO), None)
        total = previsto.resumo().total_previsto_centavos if previsto else 0
        return f"PREVISTO: {formatacao.formatar_brl(total)}"

    def _atualizar_pill_itens(self) -> None:
        if self.secao_itens is not None:
            self.secao_itens.definir_pill(status_pill(self._resumo_itens(), "info"))

    def _atualizar_pill_planejamento(self) -> None:
        if self.secao_planejamento is not None:
            self.secao_planejamento.definir_pill(
                status_pill(self.formulario.resumo_planejamento(), "info")
            )

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

    def _avisar_conflito(self) -> None:
        self.aviso.value = MENSAGEM_CONFLITO
        self.aviso.visible = True
        self.app.avisar(MENSAGEM_CONFLITO)
        self._atualizar()

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
    banner = (ft.Icons.ADD_CIRCLE, "Nova Ordem de Serviço")
    titulo_da_tela = "Nova Ordem de Serviço"
    rotulo_do_botao = "Salvar Ordem de Serviço"

    def __init__(self, app, **_params) -> None:
        super().__init__(app)
        self.previstos: EditorItens | None = None

    def tem_alteracoes(self) -> bool:
        return super().tem_alteracoes() or bool(self.previstos and self.previstos.itens)

    async def carregar(self) -> None:
        ator_id = self.app.sessao.ator_id
        # listar_tipos recusa o papel usuario: a rota digitada mostra a mensagem genérica.
        tipos = await self.app.chamar(ordens.listar_tipos, ator_id, erros_tratados=(ErroPermissao,))
        if not tipos.ok:  # recusa do serviço (já registrada por ele no log)
            self._mostrar_mensagem(self.app.MENSAGEM_GENERICA, rotas.HOME, "Voltar para a lista")
            self._atualizar()
            return
        filiais = await self.app.chamar(ordens.listar_filiais, ator_id)
        categorias = await self.app.chamar(custos.listar_categorias, ator_id)
        if filiais.ok and categorias.ok:
            self.formulario = FormularioOs(self.app, filiais.valor, tipos=tipos.valor)
            self.previstos = EditorItens(
                self.app,
                custos.FASE_PREVISTO,
                categorias.valor,
                titulo=TITULO_PREVISTOS,
                filial_de=self._filial_escolhida,
            )
            self.editores = [self.previstos]
            self._mostrar_formulario()
        else:
            self._mostrar_mensagem(
                "Não foi possível abrir o formulário.", rotas.HOME, "Voltar para a lista"
            )
        self._atualizar()

    def _filial_escolhida(self) -> int | None:
        valor = self.formulario.filial.value if self.formulario else None
        return int(valor) if valor else None

    async def _gravar(self, valores: dict) -> None:
        campos = {**self.formulario.campos, "itens_previstos": AlvoDeErro(self.previstos)}
        resultado = await self.app.chamar(
            partial(
                ordens.criar_os,
                tipo_id=valores["tipo_id"],
                prioridade=valores["prioridade"],
            ),
            self.app.sessao.ator_id,
            valores["titulo"],
            valores["descricao"],
            formularios.para_entrada(self.previstos.itens),
            valores["tempo_previsto_minutos"],
            valores["filial_id"],
            campos=campos,
        )
        if resultado.ok:
            self.formulario.marcar_como_salvo()
            self.previstos.definir_itens([])  # nada mais a perder ao sair
            await self.app.atualizar_contadores()
            await self.app.ir(
                rotas.rota_os(resultado.valor.id), mensagem="Ordem de Serviço criada."
            )


class EditarOs(_TelaDeFormulario):
    sugerir_prioridade = False  # Assumir: a prioridade começa na urgência (prompt 24)

    titulo_da_tela = "Alterar Ordem de Serviço"
    rotulo_do_botao = "Salvar alterações"

    def __init__(self, app, os_id: int, **_params) -> None:
        super().__init__(app)
        self.os_id = os_id
        self.os = None

    async def carregar(self) -> None:
        ator_id = self.app.sessao.ator_id
        # listar_tipos recusa o papel usuario: a rota digitada mostra a mensagem genérica.
        tipos = await self.app.chamar(ordens.listar_tipos, ator_id, erros_tratados=(ErroPermissao,))
        if not tipos.ok:
            self._mostrar_mensagem(self.app.MENSAGEM_GENERICA, rotas.rota_os(self.os_id), "Voltar")
            self._atualizar()
            return
        resultado = await self.app.chamar(
            ordens.obter_os, ator_id, self.os_id, erros_tratados=(ErroNaoEncontrado,)
        )
        if isinstance(resultado.erro, ErroNaoEncontrado):
            self._mostrar_mensagem(
                "Ordem de Serviço não encontrada.", rotas.HOME, "Voltar para a lista"
            )
        elif resultado.ok and not resultado.valor.acoes.pode_editar:
            # A rota foi aberta sem permissão: o serviço diz que não pode (acoes).
            self._mostrar_mensagem(
                self.app.MENSAGEM_GENERICA,
                rotas.rota_os(self.os_id),
                "Voltar para a Ordem de Serviço",
            )
        elif resultado.ok:
            os_ = resultado.valor
            filiais = await self.app.chamar(ordens.listar_filiais, ator_id)
            categorias = await self.app.chamar(custos.listar_categorias, ator_id)
            if filiais.ok and categorias.ok:
                self.os = os_
                self.formulario = FormularioOs(
                    self.app,
                    filiais.valor,
                    os=os_,
                    com_realizado=os_.acoes.pode_editar_realizado,
                    tipos=tipos.valor,
                    sugerir_prioridade=self.sugerir_prioridade,
                )
                self.editores = [
                    EditorItens(
                        self.app,
                        custos.FASE_PREVISTO,
                        categorias.valor,
                        formularios.itens_da_fase(os_.itens, custos.FASE_PREVISTO),
                        titulo=TITULO_PREVISTOS,
                        somente_leitura=not os_.acoes.pode_editar_itens_previstos,
                        ao_gravar=partial(self._gravar_item, custos.FASE_PREVISTO),
                        filial_de=lambda: os_.filial_id,
                    )
                ]
                if os_.acoes.pode_editar_itens_realizados:
                    self.editores.append(
                        EditorItens(
                            self.app,
                            custos.FASE_REALIZADO,
                            categorias.valor,
                            formularios.itens_da_fase(os_.itens, custos.FASE_REALIZADO),
                            titulo=TITULO_REALIZADOS,
                            ao_gravar=partial(self._gravar_item, custos.FASE_REALIZADO),
                            filial_de=lambda: os_.filial_id,
                        )
                    )
                self._mostrar_formulario()
        if self.formulario is None and len(self.conteudo.controls) == 1:
            # Nada foi mostrado ainda: a carga falhou (o aviso genérico já apareceu).
            self._mostrar_mensagem(
                "Não foi possível abrir o formulário.", rotas.HOME, "Voltar para a lista"
            )
        self._atualizar()

    async def _gravar_item(self, fase: str, operacao: str, antes, depois) -> bool:
        """Cada mudança de item é gravada na hora pelos serviços de item; a tela recarrega."""
        ator_id = self.app.sessao.ator_id
        versao = self.os.versao
        if operacao == ADICIONAR:
            chamada = (
                custos.adicionar_item,
                ator_id,
                self.os_id,
                versao,
                fase,
                depois.categoria_id,
                depois.descricao,
                depois.quantidade,
                depois.valor_unitario_centavos,
            )
            mensagem = "Item incluído."
        elif operacao == EDITAR:
            chamada = (
                custos.editar_item,
                ator_id,
                self.os_id,
                antes.id,
                versao,
                formularios.alteracoes_do_item(antes, depois),
            )
            mensagem = "Item alterado."
        else:
            chamada = (custos.remover_item, ator_id, self.os_id, antes.id, versao)
            mensagem = "Item removido."
        resultado = await self.app.chamar(
            *chamada, erros_tratados=(ErroConflito, ErroPermissao, ErroNaoEncontrado)
        )
        if resultado.ok:
            self.os = resultado.valor  # nova versão, itens e totais calculados pelo servidor
            for editor in self.editores:
                editor.definir_itens(formularios.itens_da_fase(self.os.itens, editor.fase))
            self.app.avisar(mensagem)
            return True
        if isinstance(resultado.erro, ErroConflito):
            self._avisar_conflito()
        elif isinstance(resultado.erro, ErroPermissao | ErroNaoEncontrado):
            self.app.avisar(self.app.MENSAGEM_GENERICA)
        return False

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
            await self.app.ir(destino, mensagem="Ordem de Serviço alterada.")
        elif isinstance(resultado.erro, ErroConflito):
            self._avisar_conflito()
        elif isinstance(resultado.erro, ErroPermissao | ErroNaoEncontrado):
            self.app.avisar(self.app.MENSAGEM_GENERICA)


class AssumirOs(EditarOs):
    """Assumir solicitação (/os/{id}/assumir): a solicitação no topo, só leitura; tipo,
    prioridade e previsto; 'Salvar' ou 'Salvar e iniciar execução'."""

    titulo_da_tela = "Assumir solicitação"
    sugerir_prioridade = True
    rotulo_do_botao = "Salvar"

    def __init__(self, app, os_id: int, **_params) -> None:
        super().__init__(app, os_id)
        self.botao_iniciar = basicos.botao_primario(
            "Salvar e iniciar execução", ft.Icons.PLAY_ARROW, self._salvar_e_iniciar
        )
        self.botao = basicos.botao_secundario("Salvar", ft.Icons.SAVE, self._salvar)
        self.pendencias = ft.Text(
            "", color=theme.COR_ERRO, size=theme.FONTE_SUBTITULO, visible=False
        )

    def _mostrar_formulario(self) -> None:
        d = self.os
        pedido = basicos.cartao(
            ft.Row(
                [
                    basicos.rotulo_valor("Número", d.numero),
                    basicos.rotulo_valor("Solicitante", d.criado_por_nome),
                    basicos.selo_status(d.status),
                ],
                wrap=True,
                spacing=theme.ESPACO_G,
                run_spacing=theme.ESPACO_P,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
        super()._mostrar_formulario()
        self.conteudo.controls = [
            *self.conteudo.controls[:1],  # título da tela
            pedido,
            *self.conteudo.controls[1:-1],
            self.pendencias,
            self.botao_iniciar,
            self.botao,
        ]

    async def _salvar_e_iniciar(self, _e=None) -> None:
        if self.botao_iniciar.disabled or self.formulario is None:
            return
        self.pendencias.visible = False
        valores = self.formulario.ler()
        if valores is None:
            self._atualizar()
            return
        self.botao_iniciar.disabled = True
        self._atualizar()
        try:
            alteracoes = self.formulario.alteracoes(valores)
            if alteracoes:
                salvo = await self.app.chamar(
                    ordens.editar_os,
                    self.app.sessao.ator_id,
                    self.os_id,
                    self.os.versao,
                    alteracoes,
                    campos=self.formulario.campos,
                    erros_tratados=(ErroConflito, ErroPermissao, ErroNaoEncontrado),
                )
                if not salvo.ok:
                    if isinstance(salvo.erro, ErroConflito):
                        self._avisar_conflito()
                    elif isinstance(salvo.erro, ErroPermissao | ErroNaoEncontrado):
                        self.app.avisar(self.app.MENSAGEM_GENERICA)
                    return
                self.os = salvo.valor
                self.formulario.marcar_como_salvo()
            iniciado = await self.app.chamar(
                ordens.iniciar_execucao,
                self.app.sessao.ator_id,
                self.os_id,
                self.os.versao,
                erros_tratados=(ErroValidacao, ErroConflito, ErroPermissao, ErroNaoEncontrado),
            )
            if iniciado.ok:
                self.formulario.marcar_como_salvo()
                await self.app.atualizar_contadores()
                await self.app.ir(rotas.rota_os(self.os_id), mensagem="Execução iniciada.")
            elif isinstance(iniciado.erro, ErroValidacao):
                # O serviço recusou: mostra o que falta (texto do próprio serviço).
                self.pendencias.value = iniciado.erro.mensagem
                self.pendencias.visible = True
            elif isinstance(iniciado.erro, ErroConflito):
                self._avisar_conflito()
            else:
                self.app.avisar(self.app.MENSAGEM_GENERICA)
        finally:
            self.botao_iniciar.disabled = False
            self._atualizar()
