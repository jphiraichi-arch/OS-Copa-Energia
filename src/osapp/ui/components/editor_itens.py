"""Editor de itens de custo de uma fase (previsto ou realizado).

Dois modos:
- local (``ao_gravar`` é None): os itens ficam só na tela até o botão da tela gravar
  tudo de uma vez (Criar e Concluir Ordem de Serviço);
- gravado: cada inclusão, alteração ou remoção chama ``ao_gravar``, que usa os serviços
  de item, recarrega a Ordem de Serviço e devolve True se gravou (Alterar).

Os subtotais são uma prévia calculada com ``custos.calcular_resumo`` (sem float).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import flet as ft

from osapp import formatacao
from osapp.services import custos
from osapp.services.erros import ErroPermissao, ErroValidacao
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
ROTULO_SEM_GASTO = "Sem gasto"
TEXTO_SEM_GASTO = "Fase marcada Sem gasto: nenhum custo."
ROTULO_TOTAL = "Total"
SUGESTAO_MIN_CARACTERES = 2
SUGESTAO_PAUSA_S = 0.3  # pausa na digitação antes de buscar sugestões

# (operação, item antes, item depois) -> True se gravou.
Gravar = Callable[
    [str, formularios.ItemLocal | None, formularios.ItemLocal | None], Awaitable[bool]
]


@dataclass
class EstadoFase:
    """Regras de uma fase de custo na tela (prompt 31/41), sem Flet: a marca 'Sem gasto' e
    os itens nunca juntos. Mesma lógica nas três telas (Nova OS, Alterar, Concluir)."""

    n_itens: int = 0
    sem_gasto: bool = False

    @property
    def pode_adicionar(self) -> bool:
        return not self.sem_gasto

    def marcar(self, valor: bool) -> str:
        """'aplicado' ou 'confirmar' (marcar com itens pergunta antes de removê-los)."""
        if valor and self.n_itens:
            return "confirmar"
        self.sem_gasto = valor
        return "aplicado"

    def trocar_por_sem_gasto(self) -> None:
        self.n_itens, self.sem_gasto = 0, True

    def adicionar(self) -> None:
        """Incluir um item desmarca 'Sem gasto'."""
        self.n_itens += 1
        self.sem_gasto = False

    def remover(self) -> None:
        self.n_itens = max(self.n_itens - 1, 0)

    @property
    def coerente(self) -> bool:
        return not (self.sem_gasto and self.n_itens)


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
        filial_de: Callable[[], int | None] | None = None,
        com_sem_gasto: bool = False,
        sem_gasto: bool = False,
        ao_sem_gasto: Callable[[bool, bool], Awaitable[bool]] | None = None,
    ) -> None:
        """``com_sem_gasto`` mostra a opção 'Sem gasto' (prompt 31). Modo gravado:
        ``ao_sem_gasto(valor, trocar)`` chama o serviço (trocar = remover os itens e marcar)
        e devolve True se gravou. Modo local: a marca fica na tela até o botão gravar."""
        self.app = app
        self.com_sem_gasto = com_sem_gasto
        self._sem_gasto = sem_gasto
        self._ao_sem_gasto = ao_sem_gasto
        # Filial das sugestões de descrição (prompt 22); None: sem sugestões.
        self.filial_de = filial_de
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

    @property
    def sem_gasto(self) -> bool:
        return self._sem_gasto

    def definir_sem_gasto(self, valor: bool) -> None:
        self._sem_gasto = valor
        self._redesenhar()

    def definir_itens(self, itens: list[formularios.ItemLocal]) -> None:
        self._itens = list(itens)
        self._redesenhar()

    def acrescentar_copias(self, itens: list[formularios.ItemLocal]) -> None:
        """Acrescenta cópias não gravadas (botão 'Copiar itens previstos')."""
        copias = formularios.copiar_itens(itens, self.fase, 0)
        if copias:
            self._sem_gasto = False  # itens e Sem gasto nunca juntos
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

    def observar(self, ao_mudar: Callable[[], None]) -> None:
        """Avisa ``ao_mudar`` depois de cada mudança (além do aviso dado na criação)."""
        anterior = self._ao_mudar

        def ambos() -> None:
            if anterior:
                anterior()
            ao_mudar()

        self._ao_mudar = ambos

    def _avisar_mudanca(self) -> None:
        if self._ao_mudar:
            self._ao_mudar()

    # --- Desenho ----------------------------------------------------------------------

    def _montar(self) -> None:
        controles: list[ft.Control] = [basicos.titulo(self.titulo, theme.FONTE_CORPO + 2)]
        if self.com_sem_gasto:
            controles.append(
                ft.Checkbox(
                    label=ROTULO_SEM_GASTO,
                    value=self._sem_gasto,
                    disabled=self.somente_leitura,
                    active_color=theme.COR_PRIMARIO,
                    label_style=ft.TextStyle(color=theme.COR_TITULO, size=theme.FONTE_CORPO),
                    on_change=lambda e: self.app.page.run_task(
                        self._ao_mudar_sem_gasto, bool(e.control.value)
                    ),
                )
            )
        if self._sem_gasto:
            # Marcada: sem lista nem botão de incluir (prompt 31).
            controles += [basicos.subtitulo(TEXTO_SEM_GASTO), self.erro]
            self.controle.controls = controles
            return
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

    async def _ao_mudar_sem_gasto(self, valor: bool) -> None:
        if EstadoFase(len(self._itens), self._sem_gasto).marcar(valor) == "confirmar":
            n = len(self._itens)

            async def trocar() -> None:
                await self._aplicar_sem_gasto(True, trocar=True)

            self._redesenhar()  # volta a caixa até a confirmação
            self.app.confirmar(
                "Marcar Sem gasto?",
                f"Remover os {n} itens e marcar Sem gasto?",
                "Remover e marcar",
                trocar,
                rotulo_cancelar="Voltar",
            )
            return
        await self._aplicar_sem_gasto(valor, trocar=False)

    async def _aplicar_sem_gasto(self, valor: bool, trocar: bool) -> None:
        if self._ao_sem_gasto is not None:  # modo gravado: o serviço decide
            if not await self._ao_sem_gasto(valor, trocar):
                self._redesenhar()  # recusado: a caixa volta ao estado anterior
                return
        elif trocar:
            self._itens = []
        self._sem_gasto = valor
        self.marcar_erro(None)
        self._redesenhar()
        self._avisar_mudanca()

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
            estado = EstadoFase(len(self._itens) - 1, self._sem_gasto)
            estado.adicionar()
            self._sem_gasto = estado.sem_gasto  # incluir item desmarca 'Sem gasto'
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
            on_change=self._ao_digitar_descricao,
        )
        # Sugestões de descrições já usadas na filial: lista sob o campo (prompt 22).
        self.sugestoes = basicos.coluna([], espaco=0)
        self.sugestoes.visible = False
        self._geracao_sugestoes = 0
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
        return (self.app.page.width or 0) < theme.LARGURA_CELULAR_MAX

    def mostrar(self) -> None:
        titulo = TITULO_EDITAR if self.item else TITULO_NOVO
        campos = [
            ft.Row([self.categoria]),
            self.descricao,
            self.sugestoes,
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

    # --- Sugestões de descrição -------------------------------------------------------

    def _ao_digitar_descricao(self, e) -> None:
        self._ao_digitar(e)
        if self.editor.filial_de is None or self.app.sessao.e_usuario:
            return
        self._geracao_sugestoes += 1
        self.app.page.run_task(self._sugerir, self._geracao_sugestoes, self.descricao.value or "")

    async def _sugerir(self, geracao: int, termo: str) -> None:
        """Espera a pausa na digitação e busca as sugestões; resultados velhos são
        descartados pela ``geracao``."""
        filial_id = self.editor.filial_de()
        if len(termo.strip()) < SUGESTAO_MIN_CARACTERES or filial_id is None:
            self._mostrar_sugestoes([])
            return
        await asyncio.sleep(SUGESTAO_PAUSA_S)
        if geracao != self._geracao_sugestoes:
            return
        resultado = await self.app.chamar(
            custos.sugerir_descricoes,
            self.app.sessao.ator_id,
            filial_id,
            termo,
            erros_tratados=(ErroPermissao, ErroValidacao),
        )
        if geracao != self._geracao_sugestoes or not resultado.ok:
            return
        atual = (self.descricao.value or "").strip()
        self._mostrar_sugestoes([t for t in resultado.valor if t != atual])

    def _mostrar_sugestoes(self, textos_: list[str]) -> None:
        self.sugestoes.controls = [self._opcao(texto) for texto in textos_]
        self.sugestoes.visible = bool(textos_)
        _atualizar(self.sugestoes)

    def _opcao(self, texto: str) -> ft.Control:
        async def escolher(_e=None, texto=texto) -> None:
            self._geracao_sugestoes += 1  # descarta buscas ainda em andamento
            self.descricao.value = texto
            self.descricao.error = None
            _atualizar(self.descricao)
            self._mostrar_sugestoes([])

        return ft.Container(
            content=ft.Text(texto, color=theme.COR_TITULO, size=theme.FONTE_CORPO),
            height=theme.ALVO_TOQUE_MIN + 1,  # 48 px tocáveis + 1 px da linha divisória
            alignment=ft.Alignment.CENTER_LEFT,
            padding=ft.Padding.symmetric(horizontal=theme.ESPACO_M),
            bgcolor=theme.COR_CAMPO_FUNDO,
            border=ft.Border.only(bottom=ft.BorderSide(width=1, color=theme.COR_CONTORNO)),
            ink=True,
            on_click=escolher,
        )

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


# Prompt 41: o nome da seção compartilhada (previsto em Nova OS e Alterar, realizado em
# Concluir). EditorItens continua valendo como nome antigo.
SecaoItensCusto = EditorItens
