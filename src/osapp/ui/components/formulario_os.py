"""Campos da Ordem de Serviço, usados por Criar, Alterar e Assumir.

Os campos ficam agrupados por seção (ui/secoes.py) em ``partes``; a tela monta os
SecaoCards. Os itens de custo ficam no editor de itens (components/editor_itens.py).
"""

from __future__ import annotations

import flet as ft

from osapp import formatacao
from osapp.services import ordens
from osapp.ui import formularios, rotulos, secoes, textos, theme
from osapp.ui.components import basicos
from osapp.ui.components.campos import CampoDuracao, CampoHora
from osapp.ui.components.chips import GrupoChips


def lista_suspensa(rotulo: str, opcoes, valor, on_select=None, disabled=False) -> ft.Dropdown:
    return ft.Dropdown(
        label=rotulo,
        options=opcoes,
        value=valor,
        on_select=on_select,
        disabled=disabled,
        expand=True,
        color=theme.COR_TITULO,
        bgcolor=theme.COR_CARTAO,
        filled=True,
        fill_color=theme.COR_CAMPO_FUNDO,
        border_color=theme.COR_CONTORNO,
        border_radius=theme.RAIO_BOTAO,
        label_style=ft.TextStyle(color=theme.COR_SUBTITULO),
    )


class FormularioOs:
    """``os`` (OsDetalhe) preenche os valores ao alterar.

    ``com_realizado`` mostra também início, fim e descrição do realizado (administrador
    em Ordem de Serviço concluída). A trava da filial é só visual: o serviço decide.
    """

    def __init__(
        self,
        app,
        filiais,
        os=None,
        com_realizado: bool = False,
        tipos=(),
        ao_mudar_planejamento=None,
        sugerir_prioridade: bool = False,
    ) -> None:
        self.app = app
        self._ao_mudar_planejamento = ao_mudar_planejamento
        self.tz = app.config.tz
        self.com_realizado = com_realizado and os is not None
        # Título e descrição de uma solicitação são do solicitante: só leitura aqui.
        self.texto_editavel = not (os and os.origem == ordens.ORIGEM_SOLICITACAO)
        limpar = self._limpar_erro

        self.titulo = basicos.campo_texto(
            "Título",
            value=os.titulo if os else "",
            max_length=ordens.TITULO_MAX,
            on_change=limpar,
            read_only=not self.texto_editavel,
        )
        self.descricao = basicos.campo_texto(
            "Descrição do problema e do serviço",
            value=os.descricao if os else "",
            multiline=True,
            min_lines=3,
            max_lines=8,
            max_length=ordens.DESCRICAO_MAX,
            on_change=limpar,
            read_only=not self.texto_editavel,
        )
        # Escolhas pequenas: chips (tipo e prioridade).
        self.tipo = GrupoChips(
            [(t.id, t.nome) for t in tipos],
            os.tipo_id if os else None,
            ao_mudar=self._avisar_planejamento,
        )
        # Prompt 24 (Assumir): sem prioridade escolhida, os chips começam na urgência do
        # solicitante (mesma escala). Esse valor conta como o original: se ninguém mexer,
        # nada é gravado aqui e o serviço copia a urgência ao iniciar (com o evento).
        self.prioridade_sugerida = (
            os.urgencia
            if sugerir_prioridade and os is not None and os.prioridade is None and os.urgencia
            else None
        )
        self.prioridade = GrupoChips(
            [(n, rotulos.nivel(n)) for n in ordens.NIVEIS],
            (os.prioridade or self.prioridade_sugerida) if os else None,
            ao_mudar=self._avisar_planejamento,
        )
        self.tempo = CampoDuracao(
            "Tempo previsto (horas:minutos)",
            (os.tempo_previsto_minutos or 0) if os else 0,
            ao_mudar=self._avisar_planejamento,
        )
        filial_inicial = os.filial_id if os else app.sessao.filial_id
        self.filial = lista_suspensa(
            "Filial",
            [ft.DropdownOption(key=str(f.id), text=f"{f.codigo} - {f.nome}") for f in filiais],
            str(filial_inicial) if filial_inicial is not None else None,
            disabled=not app.sessao.e_admin,  # trava visual; quem decide é o serviço
        )
        # Controles de cada seção (a tela decide quais seções desenhar).
        self.partes: dict[str, list[ft.Control]] = {
            secoes.SOLICITACAO: [self.titulo, self.descricao, ft.Row([self.filial])],
            secoes.PLANEJAMENTO: [
                _rotulo_de_grupo("Tipo de manutenção"),
                self.tipo.controle,
                _rotulo_de_grupo("Prioridade"),
                *(
                    [_rotulo_de_grupo(textos.PRIORIDADE_SUGERIDA)]
                    if self.prioridade_sugerida
                    else []
                ),
                self.prioridade.controle,
                self.tempo.controle,
            ],
        }
        # Nome do campo no serviço -> controle onde a mensagem de ErroValidacao aparece.
        self.campos: dict[str, ft.Control] = {
            "titulo": self.titulo,
            "descricao": self.descricao,
            "tempo_previsto_minutos": self.tempo.controle,
            "filial_id": _ErroNaLista(self.filial),
            "tipo_id": self.tipo,
            "prioridade": self.prioridade,
        }

        if self.com_realizado:
            data_ini, _ = formularios.partes_locais(os.inicio_realizado, self.tz)
            data_fim, _ = formularios.partes_locais(os.fim_realizado, self.tz)
            self.inicio_data = self._campo_data("Início - data (dd/mm/aaaa)", data_ini)
            self.inicio_hora = CampoHora("Início - hora", self._hora_local(os.inicio_realizado))
            self.fim_data = self._campo_data("Fim - data (dd/mm/aaaa)", data_fim)
            self.fim_hora = CampoHora("Fim - hora", self._hora_local(os.fim_realizado))
            self.descricao_realizado = basicos.campo_texto(
                "Descrição do que foi feito",
                value=os.descricao_realizado or "",
                multiline=True,
                min_lines=3,
                max_lines=8,
                max_length=ordens.DESCRICAO_MAX,
                on_change=limpar,
            )
            self.partes[secoes.CONCLUSAO] = [
                self.inicio_data,
                self.inicio_hora.controle,
                self.fim_data,
                self.fim_hora.controle,
                self.descricao_realizado,
            ]
            self.campos.update(
                {
                    "inicio_realizado": self.inicio_data,
                    "fim_realizado": self.fim_hora.controle,
                    "descricao_realizado": self.descricao_realizado,
                }
            )

        self._inicial = self._digitado()
        self._original = self.ler(marcar_erros=False) if os else None

    def _hora_local(self, instante):
        from zoneinfo import ZoneInfo

        return instante.astimezone(ZoneInfo(self.tz)).time().replace(second=0, microsecond=0)

    def _campo_data(self, rotulo: str, valor: str) -> ft.TextField:
        return basicos.campo_texto(
            rotulo,
            value=valor,
            hint_text="dd/mm/aaaa",
            keyboard_type=ft.KeyboardType.DATETIME,
            on_change=self._limpar_erro,
        )

    # --- Eventos dos campos -----------------------------------------------------------

    def _limpar_erro(self, e) -> None:
        if e.control.error:
            e.control.error = None
            e.control.update()

    def observar_planejamento(self, ao_mudar) -> None:
        self._ao_mudar_planejamento = ao_mudar

    def _avisar_planejamento(self) -> None:
        if self._ao_mudar_planejamento:
            self._ao_mudar_planejamento()

    def resumo_planejamento(self) -> str:
        """Texto do StatusPill da seção de planejamento: 'PREVISTO: 1:30' ou 'A DEFINIR'."""
        minutos = self.tempo.valor
        if not minutos:
            return "PREVISTO: A DEFINIR"
        return f"PREVISTO: {formatacao.formatar_duracao(minutos)}"

    # --- Leitura ----------------------------------------------------------------------

    def _digitado(self) -> dict[str, str]:
        """Texto atual de cada campo, para saber se há alterações não salvas."""
        valores = {
            "titulo": self.titulo.value or "",
            "descricao": self.descricao.value or "",
            "tempo": self.tempo.controle.value or "",
            "filial": self.filial.value or "",
            "tipo": str(self.tipo.valor or ""),
            "prioridade": self.prioridade.valor or "",
        }
        if self.com_realizado:
            valores.update(
                inicio_data=self.inicio_data.value or "",
                inicio_hora=self.inicio_hora.controle.value or "",
                fim_data=self.fim_data.value or "",
                fim_hora=self.fim_hora.controle.value or "",
                descricao_realizado=self.descricao_realizado.value or "",
            )
        return valores

    def tem_alteracoes(self) -> bool:
        return self._digitado() != self._inicial

    def ler(self, marcar_erros: bool = True) -> dict | None:
        """Valores prontos para o serviço, ou None se algum campo não pôde ser lido.

        O previsto (tempo, tipo, prioridade) é opcional aqui: iniciar a
        execução é que exige tudo. Erros locais (máscara de hora, data) aparecem sob o
        campo. O serviço valida tudo de novo.
        """
        erros: list[tuple[object, str]] = []
        if self.tempo.erro:
            erros.append((self.tempo.controle, self.tempo.erro))
        valores: dict = {
            "tempo_previsto_minutos": self.tempo.valor or None,  # 0:00 = não informado
            "filial_id": int(self.filial.value) if self.filial.value else None,
            "tipo_id": self.tipo.valor,
            "prioridade": self.prioridade.valor,
        }
        if self.texto_editavel:
            valores["titulo"] = (self.titulo.value or "").strip()
            valores["descricao"] = (self.descricao.value or "").strip()
        if self.com_realizado:
            for nome, campo_data, campo_hora in (
                ("inicio_realizado", self.inicio_data, self.inicio_hora),
                ("fim_realizado", self.fim_data, self.fim_hora),
            ):
                try:
                    valores[nome] = formularios.instante(
                        campo_data.value, campo_hora.valor, self.tz
                    )
                except ValueError as exc:
                    alvo = campo_hora.controle if campo_hora.erro else campo_data
                    erros.append((alvo, campo_hora.erro or str(exc)))
                    valores[nome] = None
            valores["descricao_realizado"] = (self.descricao_realizado.value or "").strip()

        if marcar_erros:
            for campo in self.campos.values():
                _definir_erro(campo, None)
            if self.com_realizado:
                _definir_erro(self.inicio_hora.controle, self.inicio_hora.erro)
                _definir_erro(self.fim_data, None)
            for campo, mensagem in erros:
                _definir_erro(campo, mensagem)
            for controles in self.partes.values():
                for controle in controles:
                    _atualizar(controle)
        return None if erros else valores

    def alteracoes(self, valores: dict) -> dict:
        """Só os campos que mudaram em relação à OS carregada (para editar_os)."""
        return formularios.somente_alterados(self._original or {}, valores)

    def marcar_como_salvo(self) -> None:
        self._inicial = self._digitado()


class _ErroNaLista:
    """Dropdown mostra erro em ``error_text``; ``App.chamar`` escreve em ``error``."""

    def __init__(self, lista: ft.Dropdown) -> None:
        self.lista = lista

    @property
    def error(self) -> str | None:
        return self.lista.error_text

    @error.setter
    def error(self, mensagem: str | None) -> None:
        self.lista.error_text = mensagem

    def update(self) -> None:
        self.lista.update()


def _definir_erro(controle, mensagem: str | None) -> None:
    controle.error = mensagem


def _rotulo_de_grupo(texto: str) -> ft.Text:
    return ft.Text(texto, color=theme.COR_SUBTITULO, size=theme.FONTE_SUBTITULO)


def _atualizar(controle) -> None:
    try:
        controle.update()
    except (RuntimeError, AssertionError):
        pass  # ainda não está na página
