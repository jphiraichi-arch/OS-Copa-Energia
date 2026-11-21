"""Tela Concluir Ordem de Serviço (/os/{id}/concluir)."""

from __future__ import annotations

import flet as ft

from osapp import formatacao
from osapp.services import custos, ordens, relogio
from osapp.services.erros import ErroConflito, ErroNaoEncontrado, ErroPermissao
from osapp.ui import formularios, historico, rotas, theme
from osapp.ui.components import basicos
from osapp.ui.components.campos import CampoHora
from osapp.ui.components.editor_itens import EditorItens
from osapp.ui.views.base import Tela
from osapp.ui.views.detalhe import MENSAGEM_CONFLITO
from osapp.ui.views.os_formulario import TITULO_REALIZADOS, AlvoDeErro

ROTULO_COPIAR = "Copiar itens previstos"


class ConcluirOs(Tela):
    def __init__(self, app, os_id: int, **_params) -> None:
        self.app = app
        self.os_id = os_id
        self.tz = app.config.tz
        self.os = None
        self.realizados: EditorItens | None = None
        self._inicial: dict[str, str] | None = None
        self.conteudo = basicos.coluna([basicos.carregando()])

    def tem_alteracoes(self) -> bool:
        if self._inicial is None:
            return False
        return self._digitado() != self._inicial or bool(self.realizados.itens)

    # --- Carga ------------------------------------------------------------------------

    async def carregar(self) -> None:
        ator_id = self.app.sessao.ator_id
        resultado = await self.app.chamar(
            ordens.obter_os, ator_id, self.os_id, erros_tratados=(ErroNaoEncontrado,)
        )
        if isinstance(resultado.erro, ErroNaoEncontrado):
            self._mensagem("Ordem de Serviço não encontrada.", rotas.HOME, "Voltar para a lista")
        elif not resultado.ok:
            self._mensagem("Não foi possível abrir a tela.", rotas.HOME, "Voltar para a lista")
        elif not resultado.valor.acoes.pode_concluir:
            # A rota foi aberta sem permissão: o serviço diz que não pode (acoes).
            self._mensagem(
                self.app.MENSAGEM_GENERICA,
                rotas.rota_os(self.os_id),
                "Voltar para a Ordem de Serviço",
            )
        else:
            categorias = await self.app.chamar(custos.listar_categorias, ator_id)
            if categorias.ok:
                self.os = resultado.valor
                self._montar(categorias.valor)
            else:
                self._mensagem("Não foi possível abrir a tela.", rotas.HOME, "Voltar para a lista")
        self._atualizar()

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

    # --- Montagem ---------------------------------------------------------------------

    def _campo(self, rotulo: str, valor: str = "", **opcoes) -> ft.TextField:
        return basicos.campo_texto(rotulo, value=valor, on_change=self._ao_digitar, **opcoes)

    def _montar(self, categorias) -> None:
        d = self.os
        hoje, _hora = formularios.partes_locais(relogio.agora(), self.tz)
        data = {"hint_text": "dd/mm/aaaa", "keyboard_type": ft.KeyboardType.DATETIME}
        self.previstos = formularios.itens_da_fase(d.itens, custos.FASE_PREVISTO)
        self.realizados = EditorItens(
            self.app,
            custos.FASE_REALIZADO,
            categorias,
            titulo=TITULO_REALIZADOS,
            ao_mudar=self._atualizar_previa,
            filial_de=lambda: d.filial_id,
        )
        self.inicio_data = self._campo("Início - data (dd/mm/aaaa)", hoje, **data)
        self.inicio_hora = CampoHora("Início - hora", ao_mudar=self._atualizar_previa)
        self.fim_data = self._campo("Fim - data (dd/mm/aaaa)", hoje, **data)
        self.fim_hora = CampoHora("Fim - hora", ao_mudar=self._atualizar_previa)
        self.descricao = self._campo(
            "Descrição do que foi feito",
            multiline=True,
            min_lines=3,
            max_lines=8,
            max_length=ordens.DESCRICAO_MAX,
        )
        self.nota = self._campo(
            "Nota para o solicitante",
            multiline=True,
            min_lines=3,
            max_lines=6,
            max_length=ordens.NOTA_MAX,
            helper="O solicitante verá esta nota.",
        )
        self.previa = basicos.coluna([], espaco=theme.ESPACO_P + 4)
        self.aviso = ft.Text("", color=theme.COR_ERRO, size=theme.FONTE_SUBTITULO, visible=False)
        self.botao = basicos.botao_primario(
            "Concluir Ordem de Serviço", ft.Icons.CHECK_CIRCLE_OUTLINE, self._concluir
        )
        # Nome do campo no serviço -> controle onde a mensagem de ErroValidacao aparece.
        self.campos = {
            "itens_realizados": AlvoDeErro(self.realizados),
            "inicio_realizado": self.inicio_data,
            "fim_realizado": self.fim_hora.controle,
            "descricao_realizado": self.descricao,
            "nota_conclusao": self.nota,
        }
        self.conteudo.controls = [
            basicos.cartao(self._resumo_previsto(d)),
            basicos.cartao(
                basicos.coluna(
                    [
                        self.realizados.controle,
                        basicos.botao_secundario(ROTULO_COPIAR, ft.Icons.COPY, self._copiar),
                    ]
                )
            ),
            basicos.cartao(
                basicos.coluna(
                    [
                        basicos.titulo("Realizado"),
                        self.inicio_data,
                        self.inicio_hora.controle,
                        self.fim_data,
                        self.fim_hora.controle,
                        self.descricao,
                        self.nota,
                        self.aviso,
                    ]
                )
            ),
            basicos.cartao(
                basicos.coluna(
                    [basicos.titulo("Prévia da diferença"), self.previa],
                    espaco=theme.ESPACO_P + 4,
                )
            ),
            self.botao,
        ]
        self._calcular_previa()
        self._inicial = self._digitado()

    def _resumo_previsto(self, d) -> ft.Control:
        linhas: list[ft.Control] = [
            basicos.titulo("Previsto"),
            ft.Text(
                f"{d.numero}  ·  {d.titulo}",
                color=theme.COR_SUBTITULO,
                size=theme.FONTE_SUBTITULO,
            ),
        ]
        for item in self.previstos:
            linhas.append(
                basicos.rotulo_valor(
                    f"{item.categoria_nome} - {item.descricao}",
                    f"{formatacao.formatar_quantidade(item.quantidade)} x "
                    f"{formatacao.formatar_brl(item.valor_unitario_centavos)} = "
                    f"{formatacao.formatar_brl(item.total_centavos)}",
                )
            )
        linhas += [
            basicos.rotulo_valor(
                "Total previsto",
                formatacao.formatar_brl(d.resumo_custos.total_previsto_centavos),
            ),
            basicos.rotulo_valor(
                "Tempo previsto", formatacao.formatar_duracao(d.tempo_previsto_minutos)
            ),
        ]
        return basicos.coluna(linhas, espaco=theme.ESPACO_P + 4)

    def _digitado(self) -> dict[str, str]:
        return {
            "inicio_data": self.inicio_data.value or "",
            "inicio_hora": self.inicio_hora.controle.value or "",
            "fim_data": self.fim_data.value or "",
            "fim_hora": self.fim_hora.controle.value or "",
            "descricao": self.descricao.value or "",
            "nota": self.nota.value or "",
        }

    # --- Eventos ----------------------------------------------------------------------

    async def _copiar(self, _e=None) -> None:
        self.realizados.acrescentar_copias(self.previstos)

    def _ao_digitar(self, e) -> None:
        if e.control.error:
            e.control.error = None
            e.control.update()
        self._atualizar_previa()

    def _calcular_previa(self) -> None:
        """Diferença por categoria e no total (prévia com custos.calcular_resumo) e de tempo."""
        resumo = formularios.resumo_previa([*self.previstos, *self.realizados.itens])
        linhas: list[ft.Control] = []
        com_realizado = bool(self.realizados.itens)
        for c in resumo.por_categoria:
            linhas.append(
                basicos.rotulo_valor(
                    c.categoria_nome,
                    historico.texto_diferenca_valor(c.diferenca_centavos, c.diferenca_percentual)
                    if com_realizado
                    else "-",
                )
            )
        linhas.append(
            basicos.rotulo_valor(
                "Total",
                historico.texto_diferenca_valor(
                    resumo.diferenca_centavos, resumo.diferenca_percentual
                )
                if com_realizado
                else "-",
            )
        )
        tempo = formularios.previa_tempo(
            self.os.tempo_previsto_minutos,
            (self.inicio_data.value, self.inicio_hora.valor),
            (self.fim_data.value, self.fim_hora.valor),
            self.tz,
        )
        linhas.append(basicos.rotulo_valor("Tempo", tempo or "-"))
        self.previa.controls = linhas

    def _atualizar_previa(self) -> None:
        self._calcular_previa()
        try:
            self.previa.update()
        except RuntimeError:
            pass

    def _ler(self) -> dict | None:
        """Valores prontos para o serviço; erros de leitura local aparecem sob o campo."""
        erros: list[tuple[ft.TextField, str]] = []
        instantes = {}
        for nome, campo_data, campo_hora in (
            ("inicio", self.inicio_data, self.inicio_hora),
            ("fim", self.fim_data, self.fim_hora),
        ):
            try:
                # Digitado no fuso OS_TZ e convertido para UTC antes de chamar o serviço.
                instantes[nome] = formularios.instante(campo_data.value, campo_hora.valor, self.tz)
            except ValueError as exc:
                if campo_hora.erro:
                    erros.append((campo_hora.controle, campo_hora.erro))
                else:
                    erros.append((campo_data, str(exc)))
        for campo in (self.inicio_data, self.fim_data, self.descricao, self.nota):
            campo.error = None
        self.inicio_hora.marcar_erro(self.inicio_hora.erro)
        self.fim_hora.marcar_erro(self.fim_hora.erro)
        self.realizados.marcar_erro(None)
        for campo, mensagem in erros:
            campo.error = mensagem
        if erros:
            return None
        return {
            **instantes,
            "descricao": (self.descricao.value or "").strip(),
            "nota": (self.nota.value or "").strip(),
        }

    async def _concluir(self, _e=None) -> None:
        if self.botao.disabled:
            return
        self.aviso.visible = False
        valores = self._ler()
        if valores is None:
            self._atualizar()
            return
        self.botao.disabled = True
        self._atualizar()
        try:
            resultado = await self.app.chamar(
                ordens.concluir_os,
                self.app.sessao.ator_id,
                self.os_id,
                self.os.versao,
                formularios.para_entrada(self.realizados.itens),
                valores["inicio"],
                valores["fim"],
                valores["descricao"],
                valores["nota"],
                campos=self.campos,
                erros_tratados=(ErroConflito, ErroPermissao, ErroNaoEncontrado),
            )
            if resultado.ok:
                self._inicial = None  # nada mais a perder ao sair
                await self.app.ir(rotas.rota_os(self.os_id), mensagem="Ordem de Serviço concluída.")
            elif isinstance(resultado.erro, ErroConflito):
                self.aviso.value = MENSAGEM_CONFLITO
                self.aviso.visible = True
                self.app.avisar(MENSAGEM_CONFLITO)
            elif isinstance(resultado.erro, ErroPermissao | ErroNaoEncontrado):
                self.app.avisar(self.app.MENSAGEM_GENERICA)
        finally:
            self.botao.disabled = False
            self._atualizar()
