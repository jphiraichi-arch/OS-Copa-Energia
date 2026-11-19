"""Campos do cabeçalho da Ordem de Serviço, usados por Criar e Alterar.

Os itens de custo ficam no editor de itens (components/editor_itens.py).
"""

from __future__ import annotations

import flet as ft

from osapp.services import equipamentos, ordens
from osapp.ui import formularios, rotulos, theme
from osapp.ui.components import basicos
from osapp.ui.components.campos import CampoDuracao, CampoHora

ROTULO_OUTRO = "Outro"


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
        lista_equipamentos,
        os=None,
        com_realizado: bool = False,
        tipos=(),
    ) -> None:
        self.app = app
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
        self.tipo = lista_suspensa(
            "Tipo de manutenção",
            [ft.DropdownOption(key=str(t.id), text=t.nome) for t in tipos],
            str(os.tipo_id) if os and os.tipo_id else None,
            on_select=self._ao_escolher_lista,
        )
        self.prioridade = lista_suspensa(
            "Prioridade",
            [ft.DropdownOption(key=n, text=rotulos.nivel(n)) for n in ordens.NIVEIS],
            os.prioridade if os else None,
            on_select=self._ao_escolher_lista,
        )
        lista_equipamentos = list(lista_equipamentos)
        if os and os.equipamento_id and all(e.id != os.equipamento_id for e in lista_equipamentos):
            # Equipamento desativado depois de escolhido: continua aparecendo nesta OS.
            lista_equipamentos.append(_EquipamentoAtual(os.equipamento_id, os.equipamento or ""))
        self.equipamento = lista_suspensa(
            "Equipamento",
            self._opcoes_equipamento(lista_equipamentos),
            formularios.chave_do_equipamento(os.equipamento_id, os.equipamento_outro)
            if os
            else None,
            on_select=self._ao_escolher_equipamento,
        )
        self.equipamento_outro = basicos.campo_texto(
            "Qual equipamento?",
            value=(os.equipamento_outro or "") if os else "",
            max_length=ordens.EQUIPAMENTO_OUTRO_MAX,
            on_change=limpar,
            visible=self.equipamento.value == formularios.OPCAO_OUTRO,
        )
        self.tempo = CampoDuracao(
            "Tempo previsto (horas:minutos)", (os.tempo_previsto_minutos or 0) if os else 0
        )
        filial_inicial = os.filial_id if os else app.sessao.filial_id
        self.filial = lista_suspensa(
            "Filial",
            [ft.DropdownOption(key=str(f.id), text=f"{f.codigo} - {f.nome}") for f in filiais],
            str(filial_inicial) if filial_inicial is not None else None,
            on_select=self._ao_escolher_filial,
            disabled=not app.sessao.is_admin,  # trava visual; quem decide é o serviço
        )
        controles: list[ft.Control] = [
            self.titulo,
            self.descricao,
            ft.Row([self.filial]),
            ft.Row([self.tipo]),
            ft.Row([self.prioridade]),
            ft.Row([self.equipamento]),
            self.equipamento_outro,
            self.tempo.controle,
        ]
        # Nome do campo no serviço -> controle onde a mensagem de ErroValidacao aparece.
        self.campos: dict[str, ft.Control] = {
            "titulo": self.titulo,
            "descricao": self.descricao,
            "tempo_previsto_minutos": self.tempo.controle,
            "equipamento_outro": self.equipamento_outro,
            "equipamento_id": _ErroNaLista(self.equipamento),
            "filial_id": _ErroNaLista(self.filial),
            "tipo_id": _ErroNaLista(self.tipo),
            "prioridade": _ErroNaLista(self.prioridade),
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
            controles += [
                basicos.titulo("Realizado"),
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

        self.controle = basicos.coluna(controles)
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

    @staticmethod
    def _opcoes_equipamento(lista_equipamentos) -> list[ft.DropdownOption]:
        opcoes = [ft.DropdownOption(key=str(e.id), text=e.nome) for e in lista_equipamentos]
        return [*opcoes, ft.DropdownOption(key=formularios.OPCAO_OUTRO, text=ROTULO_OUTRO)]

    # --- Eventos dos campos -----------------------------------------------------------

    def _limpar_erro(self, e) -> None:
        if e.control.error:
            e.control.error = None
            e.control.update()

    def _ao_escolher_lista(self, e) -> None:
        if e.control.error_text:
            e.control.error_text = None
            e.control.update()

    def _ao_escolher_equipamento(self, _e=None) -> None:
        self.equipamento.error_text = None
        self.equipamento_outro.error = None
        self.equipamento_outro.visible = self.equipamento.value == formularios.OPCAO_OUTRO
        self.controle.update()

    async def _ao_escolher_filial(self, _e=None) -> None:
        """Outra filial (administrador): a lista de equipamentos passa a ser a dela."""
        if not self.filial.value:
            return
        resultado = await self.app.chamar(
            equipamentos.listar_equipamentos, self.app.sessao.ator_id, int(self.filial.value)
        )
        if not resultado.ok:
            return
        self.equipamento.options = self._opcoes_equipamento(resultado.valor)
        if self.equipamento.value != formularios.OPCAO_OUTRO:
            self.equipamento.value = None  # o equipamento escolhido era da outra filial
        self.controle.update()

    # --- Leitura ----------------------------------------------------------------------

    def _digitado(self) -> dict[str, str]:
        """Texto atual de cada campo, para saber se há alterações não salvas."""
        valores = {
            "titulo": self.titulo.value or "",
            "descricao": self.descricao.value or "",
            "equipamento": self.equipamento.value or "",
            "equipamento_outro": self.equipamento_outro.value or "",
            "tempo": self.tempo.controle.value or "",
            "filial": self.filial.value or "",
            "tipo": self.tipo.value or "",
            "prioridade": self.prioridade.value or "",
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

        O previsto (tempo, tipo, prioridade, equipamento) é opcional aqui: iniciar a
        execução é que exige tudo. Erros locais (máscara de hora, data) aparecem sob o
        campo. O serviço valida tudo de novo.
        """
        erros: list[tuple[object, str]] = []
        if self.tempo.erro:
            erros.append((self.tempo.controle, self.tempo.erro))
        valores: dict = {
            "tempo_previsto_minutos": self.tempo.valor or None,  # 0:00 = não informado
            "filial_id": int(self.filial.value) if self.filial.value else None,
            "tipo_id": int(self.tipo.value) if self.tipo.value else None,
            "prioridade": self.prioridade.value or None,
            **formularios.ler_equipamento(self.equipamento.value, self.equipamento_outro.value),
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
            self.controle.update()
        return None if erros else valores

    def alteracoes(self, valores: dict) -> dict:
        """Só os campos que mudaram em relação à OS carregada (para editar_os).

        Equipamento vai sempre em par: o serviço troca o tipo (lista ou 'Outro') junto.
        """
        mudou = formularios.somente_alterados(self._original or {}, valores)
        if "equipamento_id" in mudou or "equipamento_outro" in mudou:
            mudou["equipamento_id"] = valores["equipamento_id"]
            mudou["equipamento_outro"] = valores["equipamento_outro"]
        return mudou

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


class _EquipamentoAtual:
    def __init__(self, id_: int, nome: str) -> None:
        self.id, self.nome = id_, nome


def _definir_erro(controle, mensagem: str | None) -> None:
    controle.error = mensagem
