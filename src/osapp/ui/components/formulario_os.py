"""Formulário de OS, usado por Criar OS e Alterar OS."""

from __future__ import annotations

import flet as ft

from osapp.services import ordens
from osapp.ui import formularios, theme
from osapp.ui.components import basicos


class FormularioOs:
    """Campos do formulário. ``os`` (OsDetalhe) preenche os valores ao alterar.

    ``com_realizado`` mostra também os campos de "realizado" (administrador em OS
    concluída). A trava da filial é só visual: o serviço recusa outra filial.
    """

    def __init__(self, app, filiais, os=None, com_realizado: bool = False) -> None:
        self.app = app
        self.tz = app.config.tz
        self.com_realizado = com_realizado and os is not None
        limpar = self._limpar_erro

        self.titulo = basicos.campo_texto(
            "Título", value=os.titulo if os else "", max_length=ordens.TITULO_MAX, on_change=limpar
        )
        self.descricao = basicos.campo_texto(
            "Descrição do problema e do serviço",
            value=os.descricao if os else "",
            multiline=True,
            min_lines=3,
            max_lines=8,
            max_length=ordens.DESCRICAO_MAX,
            on_change=limpar,
        )
        self.valor = basicos.campo_texto(
            "Valor previsto (R$)",
            value=formularios.valor_para_campo(os.valor_previsto_centavos) if os else "",
            hint_text="0,00",
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=limpar,
            on_blur=self._formatar_valor,
        )
        self.tempo = basicos.campo_texto(
            "Tempo previsto (HH:MM)",
            value=formularios.tempo_para_campo(os.tempo_previsto_minutos) if os else "",
            hint_text="1:30",
            keyboard_type=ft.KeyboardType.DATETIME,
            on_change=limpar,
        )
        filial_inicial = os.filial_id if os else app.sessao.filial_id
        self.filial = ft.Dropdown(
            label="Filial",
            options=[
                ft.DropdownOption(key=str(f.id), text=f"{f.codigo} - {f.nome}") for f in filiais
            ],
            value=str(filial_inicial) if filial_inicial is not None else None,
            disabled=not app.sessao.is_admin,  # trava visual; quem decide é o serviço
            expand=True,
            color=theme.COR_TITULO,
            bgcolor=theme.COR_CARTAO,
            filled=True,
            fill_color=theme.COR_CAMPO_FUNDO,
            border_color=theme.COR_CONTORNO,
            border_radius=theme.RAIO_BOTAO,
            label_style=ft.TextStyle(color=theme.COR_SUBTITULO),
        )
        controles: list[ft.Control] = [
            self.titulo,
            self.descricao,
            self.valor,
            self.tempo,
            ft.Row([self.filial]),
        ]
        # Nome do campo no serviço -> controle onde a mensagem de ErroValidacao aparece.
        self.campos: dict[str, ft.Control] = {
            "titulo": self.titulo,
            "descricao": self.descricao,
            "valor_previsto_centavos": self.valor,
            "tempo_previsto_minutos": self.tempo,
        }

        if self.com_realizado:
            data_ini, hora_ini = formularios.partes_locais(os.inicio_realizado, self.tz)
            data_fim, hora_fim = formularios.partes_locais(os.fim_realizado, self.tz)
            self.valor_realizado = basicos.campo_texto(
                "Valor realizado (R$)",
                value=formularios.valor_para_campo(os.valor_realizado_centavos),
                keyboard_type=ft.KeyboardType.NUMBER,
                on_change=limpar,
                on_blur=self._formatar_valor,
            )
            self.inicio_data = self._campo_data("Início - data (dd/mm/aaaa)", data_ini)
            self.inicio_hora = self._campo_hora("Início - hora (HH:MM)", hora_ini)
            self.fim_data = self._campo_data("Fim - data (dd/mm/aaaa)", data_fim)
            self.fim_hora = self._campo_hora("Fim - hora (HH:MM)", hora_fim)
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
                self.valor_realizado,
                self.inicio_data,
                self.inicio_hora,
                self.fim_data,
                self.fim_hora,
                self.descricao_realizado,
            ]
            self.campos.update(
                {
                    "valor_realizado_centavos": self.valor_realizado,
                    "inicio_realizado": self.inicio_data,
                    "fim_realizado": self.fim_hora,
                    "descricao_realizado": self.descricao_realizado,
                }
            )

        self.controle = basicos.coluna(controles)
        self._inicial = self._digitado()
        self._original = self.ler(marcar_erros=False) if os else None

    def _campo_data(self, rotulo: str, valor: str) -> ft.TextField:
        return basicos.campo_texto(
            rotulo,
            value=valor,
            hint_text="dd/mm/aaaa",
            keyboard_type=ft.KeyboardType.DATETIME,
            on_change=self._limpar_erro,
        )

    def _campo_hora(self, rotulo: str, valor: str) -> ft.TextField:
        return basicos.campo_texto(
            rotulo,
            value=valor,
            hint_text="13:50",
            keyboard_type=ft.KeyboardType.DATETIME,
            on_change=self._limpar_erro,
        )

    # --- Eventos dos campos -----------------------------------------------------------

    def _limpar_erro(self, e) -> None:
        if e.control.error:
            e.control.error = None
            e.control.update()

    def _formatar_valor(self, e) -> None:
        """Ao sair do campo, mostra o valor formatado (se for válido)."""
        campo = e.control
        if not (campo.value or "").strip():
            return
        try:
            campo.value = formularios.valor_para_campo(formularios.ler_valor(campo.value))
            campo.error = None
        except ValueError as exc:
            campo.error = str(exc)
        campo.update()

    # --- Leitura ----------------------------------------------------------------------

    def _digitado(self) -> dict[str, str]:
        """Texto atual de cada campo, para saber se há alterações não salvas."""
        valores = {nome: (c.value or "") for nome, c in self._controles_de_texto().items()}
        valores["filial"] = self.filial.value or ""
        return valores

    def _controles_de_texto(self) -> dict[str, ft.TextField]:
        controles = {
            "titulo": self.titulo,
            "descricao": self.descricao,
            "valor": self.valor,
            "tempo": self.tempo,
        }
        if self.com_realizado:
            controles.update(
                valor_realizado=self.valor_realizado,
                inicio_data=self.inicio_data,
                inicio_hora=self.inicio_hora,
                fim_data=self.fim_data,
                fim_hora=self.fim_hora,
                descricao_realizado=self.descricao_realizado,
            )
        return controles

    def tem_alteracoes(self) -> bool:
        return self._digitado() != self._inicial

    def ler(self, marcar_erros: bool = True) -> dict | None:
        """Valores prontos para o serviço, ou None se algum campo não pôde ser lido.

        Erros de leitura local (dinheiro, duração, data, hora) aparecem sob o campo.
        """
        erros: list[tuple[ft.TextField, str]] = []

        def tentar(campo: ft.TextField, funcao, *args):
            try:
                return funcao(*args)
            except ValueError as exc:
                erros.append((campo, str(exc)))
                return None

        valores: dict = {
            "titulo": (self.titulo.value or "").strip(),
            "descricao": (self.descricao.value or "").strip(),
            "valor_previsto_centavos": tentar(self.valor, formularios.ler_valor, self.valor.value),
            "tempo_previsto_minutos": tentar(self.tempo, formularios.ler_tempo, self.tempo.value),
            "filial_id": int(self.filial.value) if self.filial.value else None,
        }
        if self.com_realizado:
            valores["valor_realizado_centavos"] = tentar(
                self.valor_realizado, formularios.ler_valor, self.valor_realizado.value
            )
            for nome, campo_data, campo_hora in (
                ("inicio_realizado", self.inicio_data, self.inicio_hora),
                ("fim_realizado", self.fim_data, self.fim_hora),
            ):
                dia = tentar(campo_data, formularios.ler_data, campo_data.value)
                hora = tentar(campo_hora, formularios.ler_hora, campo_hora.value)
                valores[nome] = (
                    formularios.para_utc(dia, hora, self.tz) if dia and hora is not None else None
                )
            valores["descricao_realizado"] = (self.descricao_realizado.value or "").strip()

        if marcar_erros:
            for campo in self._controles_de_texto().values():
                campo.error = None
            for campo, mensagem in erros:
                campo.error = mensagem
            self.controle.update()
        return None if erros else valores

    def alteracoes(self, valores: dict) -> dict:
        """Só os campos que mudaram em relação à OS carregada (para editar_os)."""
        return formularios.somente_alterados(self._original or {}, valores)

    def marcar_como_salvo(self) -> None:
        self._inicial = self._digitado()
