"""Tela Concluir OS (/os/{id}/concluir)."""

from __future__ import annotations

import flet as ft

from osapp import formatacao
from osapp.services import ordens, relogio
from osapp.services.erros import ErroConflito, ErroNaoEncontrado, ErroPermissao
from osapp.ui import formularios, rotas, theme
from osapp.ui.components import basicos
from osapp.ui.views.base import Tela
from osapp.ui.views.os_formulario import MENSAGEM_CONFLITO


class ConcluirOs(Tela):
    def __init__(self, app, os_id: int, **_params) -> None:
        self.app = app
        self.os_id = os_id
        self.tz = app.config.tz
        self.os = None
        self._inicial: dict[str, str] | None = None
        self.conteudo = basicos.coluna([basicos.carregando()])

    def tem_alteracoes(self) -> bool:
        return self._inicial is not None and self._digitado() != self._inicial

    # --- Carga ------------------------------------------------------------------------

    async def carregar(self) -> None:
        resultado = await self.app.chamar(
            ordens.obter_os,
            self.app.sessao.ator_id,
            self.os_id,
            erros_tratados=(ErroNaoEncontrado,),
        )
        if isinstance(resultado.erro, ErroNaoEncontrado):
            self._mensagem("OS não encontrada.", rotas.HOME, "Voltar para a lista")
        elif not resultado.ok:
            self._mensagem("Não foi possível abrir a tela.", rotas.HOME, "Voltar para a lista")
        elif not resultado.valor.acoes.pode_concluir:
            # A rota foi aberta sem permissão: o serviço diz que não pode (acoes).
            self._mensagem(
                self.app.MENSAGEM_GENERICA, rotas.rota_os(self.os_id), "Voltar para a OS"
            )
        else:
            self.os = resultado.valor
            self._montar()
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

    def _montar(self) -> None:
        d = self.os
        hoje, _hora = formularios.partes_locais(relogio.agora(), self.tz)
        data_hora = {"keyboard_type": ft.KeyboardType.DATETIME}
        self.valor = self._campo(
            "Valor realizado (R$)",
            hint_text="0,00",
            keyboard_type=ft.KeyboardType.NUMBER,
            on_blur=self._formatar_valor,
        )
        self.inicio_data = self._campo(
            "Início - data (dd/mm/aaaa)", hoje, hint_text="dd/mm/aaaa", **data_hora
        )
        self.inicio_hora = self._campo("Início - hora (HH:MM)", hint_text="13:50", **data_hora)
        self.fim_data = self._campo(
            "Fim - data (dd/mm/aaaa)", hoje, hint_text="dd/mm/aaaa", **data_hora
        )
        self.fim_hora = self._campo("Fim - hora (HH:MM)", hint_text="14:30", **data_hora)
        self.descricao = self._campo(
            "Descrição do que foi feito",
            multiline=True,
            min_lines=3,
            max_lines=8,
            max_length=ordens.DESCRICAO_MAX,
        )
        self.previa_valor = basicos.rotulo_valor("Diferença de valor", "-")
        self.previa_tempo = basicos.rotulo_valor("Diferença de tempo", "-")
        self.aviso = ft.Text("", color=theme.COR_ERRO, size=theme.FONTE_SUBTITULO, visible=False)
        self.botao = basicos.botao_primario(
            "Concluir OS", ft.Icons.CHECK_CIRCLE_OUTLINE, self._concluir
        )
        # Nome do campo no serviço -> controle onde a mensagem de ErroValidacao aparece.
        self.campos = {
            "valor_realizado_centavos": self.valor,
            "inicio_realizado": self.inicio_data,
            "fim_realizado": self.fim_hora,
            "descricao_realizado": self.descricao,
        }
        self.conteudo.controls = [
            basicos.cartao(
                basicos.coluna(
                    [
                        basicos.titulo("Previsto"),
                        ft.Text(
                            f"{d.numero}  ·  {d.titulo}",
                            color=theme.COR_SUBTITULO,
                            size=theme.FONTE_SUBTITULO,
                        ),
                        basicos.rotulo_valor(
                            "Valor previsto", formatacao.formatar_brl(d.valor_previsto_centavos)
                        ),
                        basicos.rotulo_valor(
                            "Tempo previsto",
                            formatacao.formatar_duracao(d.tempo_previsto_minutos),
                        ),
                    ],
                    espaco=theme.ESPACO_P + 4,
                )
            ),
            basicos.cartao(
                basicos.coluna(
                    [
                        basicos.titulo("Realizado"),
                        self.valor,
                        self.inicio_data,
                        self.inicio_hora,
                        self.fim_data,
                        self.fim_hora,
                        self.descricao,
                        self.aviso,
                    ]
                )
            ),
            basicos.cartao(
                basicos.coluna(
                    [basicos.titulo("Prévia da diferença"), self.previa_valor, self.previa_tempo],
                    espaco=theme.ESPACO_P + 4,
                )
            ),
            self.botao,
        ]
        self._inicial = self._digitado()

    def _digitado(self) -> dict[str, str]:
        return {
            nome: (campo.value or "")
            for nome, campo in (
                ("valor", self.valor),
                ("inicio_data", self.inicio_data),
                ("inicio_hora", self.inicio_hora),
                ("fim_data", self.fim_data),
                ("fim_hora", self.fim_hora),
                ("descricao", self.descricao),
            )
        }

    # --- Eventos ----------------------------------------------------------------------

    def _ao_digitar(self, e) -> None:
        if e.control.error:
            e.control.error = None
            e.control.update()
        self._atualizar_previa()

    def _formatar_valor(self, e) -> None:
        campo = e.control
        if not (campo.value or "").strip():
            return
        try:
            campo.value = formularios.valor_para_campo(formularios.ler_valor(campo.value))
            campo.error = None
        except ValueError as exc:
            campo.error = str(exc)
        campo.update()

    def _atualizar_previa(self) -> None:
        previa_valor, previa_tempo = formularios.previa_diferencas(
            self.os.valor_previsto_centavos,
            self.os.tempo_previsto_minutos,
            self.valor.value,
            (self.inicio_data.value, self.inicio_hora.value),
            (self.fim_data.value, self.fim_hora.value),
            self.tz,
        )
        self.previa_valor.controls[1].value = previa_valor or "-"
        self.previa_tempo.controls[1].value = previa_tempo or "-"
        self.previa_valor.update()
        self.previa_tempo.update()

    def _ler(self) -> dict | None:
        """Valores prontos para o serviço; erros de leitura local aparecem sob o campo."""
        erros: list[tuple[ft.TextField, str]] = []

        def tentar(campo: ft.TextField, funcao):
            try:
                return funcao(campo.value)
            except ValueError as exc:
                erros.append((campo, str(exc)))
                return None

        valor = tentar(self.valor, formularios.ler_valor)
        dia_inicio = tentar(self.inicio_data, formularios.ler_data)
        hora_inicio = tentar(self.inicio_hora, formularios.ler_hora)
        dia_fim = tentar(self.fim_data, formularios.ler_data)
        hora_fim = tentar(self.fim_hora, formularios.ler_hora)
        for campo in self.campos.values():
            campo.error = None
        self.inicio_hora.error = self.fim_data.error = None
        for campo, mensagem in erros:
            campo.error = mensagem
        if erros:
            return None
        return {
            "valor": valor,
            # Digitado no fuso OS_TZ e convertido para UTC antes de chamar o serviço.
            "inicio": formularios.para_utc(dia_inicio, hora_inicio, self.tz),
            "fim": formularios.para_utc(dia_fim, hora_fim, self.tz),
            "descricao": (self.descricao.value or "").strip(),
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
                valores["valor"],
                valores["inicio"],
                valores["fim"],
                valores["descricao"],
                campos=self.campos,
                erros_tratados=(ErroConflito, ErroPermissao, ErroNaoEncontrado),
            )
            if resultado.ok:
                self._inicial = self._digitado()  # nada mais a perder ao sair
                await self.app.ir(rotas.rota_os(self.os_id), mensagem="OS concluída.")
            elif isinstance(resultado.erro, ErroConflito):
                self.aviso.value = MENSAGEM_CONFLITO
                self.aviso.visible = True
                self.app.avisar(MENSAGEM_CONFLITO)
            elif isinstance(resultado.erro, ErroPermissao | ErroNaoEncontrado):
                self.app.avisar(self.app.MENSAGEM_GENERICA)
        finally:
            self.botao.disabled = False
            self._atualizar()
