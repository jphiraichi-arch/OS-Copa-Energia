"""Editor de itens de custo de uma fase (previsto ou realizado).

Dois modos:
- local (``ao_gravar`` é None): os itens ficam só na tela até o botão da tela gravar
  tudo de uma vez (Criar e Concluir Ordem de Serviço);
- gravado: cada inclusão, alteração ou remoção chama ``ao_gravar``, que usa os serviços
  de item, recarrega a Ordem de Serviço e devolve True se gravou (Alterar).

Os subtotais são uma prévia calculada com ``custos.calcular_resumo`` (sem float).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import flet as ft

from osapp import formatacao
from osapp.services import custos
from osapp.ui import formularios, theme
from osapp.ui.components import basicos
from osapp.ui.components.campos import CampoDinheiro

ADICIONAR = "adicionar"
EDITAR = "editar"
REMOVER = "remover"

ROTULO_ADICIONAR = "Adicionar item"
TITULO_NOVO = "Novo item de custo"
TITULO_EDITAR = "Alterar item de custo"
SEM_ITENS = "Nenhum item incluído."
ROTULO_TOTAL = "Total"

# (operação, item antes, item depois) -> True se gravou.
Gravar = Callable[
    [str, formularios.ItemLocal | None, formularios.ItemLocal | None], Awaitable[bool]
]


class EditorItens:
    def __init__(
        self,
        app,
        fase: str,
        categorias,
        itens: list[formularios.ItemLocal] | None = None,
        *,
        titulo: str,
        somente_leitura: bool = False,
        ao_gravar: Gravar | None = None,
        ao_mudar: Callable[[], None] | None = None,
    ) -> None:
        self.app = app
        self.fase = fase
        self.categorias = list(categorias)
        self.titulo = titulo
        self.somente_leitura = somente_leitura
        self._ao_gravar = ao_gravar
        self._ao_mudar = ao_mudar
        self._itens: list[formularios.ItemLocal] = list(itens or [])
        self._proxima_chave = -1  # itens só da tela recebem chaves negativas
        self.erro = ft.Text("", color=theme.COR_ERRO, size=theme.FONTE_PEQUENA, visible=False)
        self.controle = basicos.coluna([], espaco=theme.ESPACO_P + 4)
        self._montar()

    # --- Dados ------------------------------------------------------------------------

    @property
    def itens(self) -> list[formularios.ItemLocal]:
        return list(self._itens)

    def definir_itens(self, itens: list[formularios.ItemLocal]) -> None:
        self._itens = list(itens)
        self._redesenhar()

    def acrescentar_copias(self, itens: list[formularios.ItemLocal]) -> None:
        """Acrescenta cópias não gravadas (botão 'Copiar itens previstos')."""
        copias = formularios.copiar_itens(itens, self.fase, 0)
        for copia in copias:
            self._itens.append(_com_chave(copia, self._nova_chave()))
        self._redesenhar()
        self._avisar_mudanca()

    def marcar_erro(self, mensagem: str | None) -> None:
        """Mensagem do serviço sobre a lista inteira (ex.: 'Inclua pelo menos um item')."""
        self.erro.value = mensagem or ""
        self.erro.visible = bool(mensagem)
        _atualizar(self.erro)

    def resumo(self) -> custos.ResumoCustos:
        return formularios.resumo_previa(self._itens)

    def _nova_chave(self) -> int:
        chave = self._proxima_chave
        self._proxima_chave -= 1
        return chave

    def _avisar_mudanca(self) -> None:
        if self._ao_mudar:
            self._ao_mudar()

    # --- Desenho ----------------------------------------------------------------------

    def _montar(self) -> None:
        controles: list[ft.Control] = [basicos.titulo(self.titulo, theme.FONTE_CORPO + 2)]
        if not self._itens:
            controles.append(basicos.subtitulo(SEM_ITENS))
        por_categoria: dict[int, list[formularios.ItemLocal]] = {}
        for item in sorted(self._itens, key=lambda i: (i.categoria_ordem, i.categoria_id)):
            por_categoria.setdefault(item.categoria_id, []).append(item)
        resumo = self.resumo()
        subtotais = {linha.categoria_id: self._subtotal(linha) for linha in resumo.por_categoria}
        for categoria_id, itens in por_categoria.items():
            controles.append(
                ft.Row(
                    [
                        ft.Text(
                            itens[0].categoria_nome,
                            color=theme.COR_TITULO,
                            size=theme.FONTE_SUBTITULO,
                            weight=ft.FontWeight.BOLD,
                            expand=True,
                        ),
                        ft.Text(
                            formatacao.formatar_brl(subtotais.get(categoria_id, 0)),
                            color=theme.COR_TITULO,
                            size=theme.FONTE_SUBTITULO,
                            weight=ft.FontWeight.BOLD,
                        ),
                    ]
                )
            )
            controles += [self._linha(item) for item in itens]
        controles.append(ft.Divider(color=theme.COR_CONTORNO, height=1))
        total = (
            resumo.total_previsto_centavos
            if self.fase == custos.FASE_PREVISTO
            else resumo.total_realizado_centavos
        )
        controles.append(
            ft.Row(
                [
                    ft.Text(
                        ROTULO_TOTAL,
                        color=theme.COR_TITULO,
                        size=theme.FONTE_CORPO,
                        weight=ft.FontWeight.BOLD,
                        expand=True,
                    ),
                    ft.Text(
                        formatacao.formatar_brl(total),
                        color=theme.COR_TITULO,
                        size=theme.FONTE_CORPO,
                        weight=ft.FontWeight.BOLD,
                    ),
                ]
            )
        )
        controles.append(self.erro)
        if not self.somente_leitura:
            controles.append(
                basicos.botao_secundario(ROTULO_ADICIONAR, ft.Icons.ADD, self._ao_clicar_adicionar)
            )
        self.controle.controls = controles

    def _subtotal(self, linha: custos.ResumoCategoria) -> int:
        if self.fase == custos.FASE_PREVISTO:
            return linha.previsto_centavos
        return linha.realizado_centavos

    def _linha(self, item: formularios.ItemLocal) -> ft.Control:
        textos = ft.Column(
            [
                ft.Text(item.descricao, color=theme.COR_TITULO, size=theme.FONTE_CORPO),
                ft.Text(
                    f"{formatacao.formatar_quantidade(item.quantidade)} x "
                    f"{formatacao.formatar_brl(item.valor_unitario_centavos)}",
                    color=theme.COR_SUBTITULO,
                    size=theme.FONTE_PEQUENA,
                ),
            ],
            spacing=2,
            expand=True,
        )
        controles: list[ft.Control] = [
            textos,
            ft.Text(
                formatacao.formatar_brl(item.total_centavos),
                color=theme.COR_TITULO,
                size=theme.FONTE_CORPO,
            ),
        ]
        if not self.somente_leitura:

            async def editar(_e=None, item=item) -> None:
                self._abrir(item)

            async def remover(_e=None, item=item) -> None:
                self._confirmar_remocao(item)

            controles += [
                ft.IconButton(
                    icon=ft.Icons.EDIT_OUTLINED,
                    icon_color=theme.COR_SUBTITULO,
                    tooltip="Alterar item",
                    on_click=editar,
                ),
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color=theme.COR_ERRO,
                    tooltip="Remover item",
                    on_click=remover,
                ),
            ]
        return ft.Row(controles, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def _redesenhar(self) -> None:
        self._montar()
        _atualizar(self.controle)

    # --- Inclusão e alteração ---------------------------------------------------------

    async def _ao_clicar_adicionar(self, _e=None) -> None:
        self._abrir(None)

    def _abrir(self, item: formularios.ItemLocal | None) -> None:
        DialogoItem(self, item).mostrar()

    async def _salvar(
        self, antes: formularios.ItemLocal | None, depois: formularios.ItemLocal
    ) -> bool:
        operacao = ADICIONAR if antes is None else EDITAR
        if self._ao_gravar is not None:
            if antes is not None and not formularios.alteracoes_do_item(antes, depois):
                return True  # nada mudou
            return await self._ao_gravar(operacao, antes, depois)
        if antes is None:
            self._itens.append(depois)
        else:
            self._itens = [depois if i.chave == antes.chave else i for i in self._itens]
        self.marcar_erro(None)
        self._redesenhar()
        self._avisar_mudanca()
        return True

    # --- Remoção ----------------------------------------------------------------------

    def _confirmar_remocao(self, item: formularios.ItemLocal) -> None:
        async def remover() -> None:
            if self._ao_gravar is not None:
                await self._ao_gravar(REMOVER, item, None)
                return
            self._itens = [i for i in self._itens if i.chave != item.chave]
            self._redesenhar()
            self._avisar_mudanca()

        self.app.confirmar(
            "Remover item",
            f"Remover o item '{item.descricao}' ({formatacao.formatar_brl(item.total_centavos)})?",
            "Remover",
            remover,
        )


class DialogoItem:
    """Campos de um item: folha inferior no celular, diálogo em telas largas."""

    def __init__(self, editor: EditorItens, item: formularios.ItemLocal | None) -> None:
        self.editor = editor
        self.item = item
        self.app = editor.app
        self.categoria = ft.Dropdown(
            label="Categoria",
            options=[ft.DropdownOption(key=str(c.id), text=c.nome) for c in editor.categorias],
            value=str(item.categoria_id) if item else None,
            on_select=self._ao_escolher_categoria,
            expand=True,
            color=theme.COR_TITULO,
            bgcolor=theme.COR_CARTAO,
            filled=True,
            fill_color=theme.COR_CAMPO_FUNDO,
            border_color=theme.COR_CONTORNO,
            border_radius=theme.RAIO_BOTAO,
            label_style=ft.TextStyle(color=theme.COR_SUBTITULO),
        )
        self.descricao = basicos.campo_texto(
            "Descrição",
            value=item.descricao if item else "",
            max_length=custos.DESCRICAO_ITEM_MAX,
            on_change=self._ao_digitar,
        )
        self.quantidade = basicos.campo_texto(
            "Quantidade",
            value=formularios.quantidade_para_campo(item.quantidade) if item else "1",
            hint_text="1 ou 1,5",
            on_change=self._ao_digitar,
        )
        self.valor = CampoDinheiro(
            "Valor unitário",
            item.valor_unitario_centavos if item else 0,
            ao_mudar=self._atualizar_total,
        )
        self.total = basicos.rotulo_valor("Total da linha", "-")
        self.campos = {
            "categoria_id": self.categoria,
            "descricao": self.descricao,
            "quantidade": self.quantidade,
            "valor_unitario_centavos": self.valor.controle,
        }
        self.botao = basicos.botao_primario(
            "Salvar item" if item else ROTULO_ADICIONAR, ft.Icons.CHECK, self._confirmar
        )
        self.cancelar = basicos.botao_secundario("Cancelar", None, self._cancelar)
        self.dialogo: ft.DialogControl | None = None
        self._calcular_total()

    # --- Exibição ---------------------------------------------------------------------

    def _e_celular(self) -> bool:
        return (self.app.page.width or 0) < theme.LARGURA_TRILHO_MIN

    def mostrar(self) -> None:
        titulo = TITULO_EDITAR if self.item else TITULO_NOVO
        campos = [
            ft.Row([self.categoria]),
            self.descricao,
            self.quantidade,
            self.valor.controle,
            self.total,
        ]
        if self._e_celular():
            self.dialogo = ft.BottomSheet(
                show_drag_handle=True,
                scrollable=True,
                bgcolor=theme.COR_CARTAO,
                content=ft.Container(
                    padding=ft.Padding.only(
                        left=theme.ESPACO_M,
                        right=theme.ESPACO_M,
                        bottom=theme.ESPACO_G,
                    ),
                    content=basicos.coluna(
                        [basicos.titulo(titulo), *campos, self.botao, self.cancelar]
                    ),
                ),
            )
        else:
            self.dialogo = ft.AlertDialog(
                modal=True,
                bgcolor=theme.COR_CARTAO,
                title=ft.Text(titulo, color=theme.COR_TITULO),
                content=ft.Container(width=theme.LARGURA_MAX_LOGIN, content=basicos.coluna(campos)),
                actions=[
                    ft.TextButton(
                        content="Cancelar",
                        style=theme.estilo_botao_texto(),
                        height=theme.ALVO_TOQUE_MIN,
                        on_click=self._cancelar,
                    ),
                    ft.TextButton(
                        content=self.botao.content,
                        style=theme.estilo_botao_texto(),
                        height=theme.ALVO_TOQUE_MIN,
                        on_click=self._confirmar,
                    ),
                ],
                scrollable=True,
            )
        self.app.page.show_dialog(self.dialogo)

    def _fechar(self) -> None:
        # Fecha este diálogo, e não o do topo da pilha: depois de gravar, o aviso
        # (SnackBar) também entra na pilha de diálogos da página. É o que
        # Page.pop_dialog faz, só que com o diálogo certo (flet 1.1.2, base_page.py).
        if self.dialogo is not None and self.dialogo.open:
            self.dialogo.open = False
            self.dialogo.update()

    async def _cancelar(self, _e=None) -> None:
        self._fechar()

    # --- Eventos ----------------------------------------------------------------------

    def _limpar(self, controle) -> None:
        if getattr(controle, "error", None):
            controle.error = None
        if getattr(controle, "error_text", None):
            controle.error_text = None

    def _ao_escolher_categoria(self, _e=None) -> None:
        self._limpar(self.categoria)
        _atualizar(self.categoria)

    def _ao_digitar(self, e) -> None:
        if e.control.error:
            e.control.error = None
            e.control.update()
        self._atualizar_total()

    def _calcular_total(self) -> None:
        try:
            quantidade = formularios.ler_quantidade(self.quantidade.value)
        except ValueError:
            quantidade = None
        valor = self.valor.valor
        texto = "-"
        if quantidade is not None and valor is not None:
            texto = formatacao.formatar_brl(custos.total_da_linha(quantidade, valor))
        self.total.controls[1].value = texto

    def _atualizar_total(self) -> None:
        self._calcular_total()
        _atualizar(self.total)

    def _valores(self) -> dict:
        return {
            "categoria_id": int(self.categoria.value) if self.categoria.value else None,
            "descricao": self.descricao.value,
            "quantidade": self.quantidade.value,
            "valor_unitario_centavos": self.valor.valor,
        }

    async def _confirmar(self, _e=None) -> None:
        if self.botao.disabled:
            return
        chave = self.item.chave if self.item else self.editor._nova_chave()
        item_id = self.item.id if self.item else None
        novo, erros = formularios.ler_item(
            self.editor.categorias, self.editor.fase, chave, item_id, self._valores()
        )
        self.categoria.error_text = erros.get("categoria_id")
        self.descricao.error = erros.get("descricao")
        self.quantidade.error = erros.get("quantidade")
        self.valor.marcar_erro(erros.get("valor_unitario_centavos") or self.valor.erro)
        if novo is None:
            _atualizar(self.dialogo)
            return
        self.botao.disabled = True
        _atualizar(self.dialogo)
        try:
            gravou = await self.editor._salvar(self.item, novo)
        finally:
            self.botao.disabled = False
        if gravou:
            self._fechar()
        else:
            _atualizar(self.dialogo)


def _com_chave(item: formularios.ItemLocal, chave: int) -> formularios.ItemLocal:
    from dataclasses import replace

    return replace(item, chave=chave)


def _atualizar(controle) -> None:
    try:
        controle.update()
    except (RuntimeError, AssertionError):
        pass  # ainda não está na página, ou a tela já foi trocada
