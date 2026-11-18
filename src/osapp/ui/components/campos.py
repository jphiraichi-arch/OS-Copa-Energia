"""Campos com máscara de caixa registradora: dinheiro, duração e hora do relógio.

Em cada mudança o campo guarda só os dígitos, aplica a máscara (ui/mascaras.py),
reescreve o texto e põe o cursor no fim. A validação que vale é a do serviço.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import time

import flet as ft

from osapp.ui import mascaras
from osapp.ui.components import basicos


class _CampoMascarado:
    def __init__(
        self,
        rotulo: str,
        aplicar: Callable[[str], mascaras.Mascarado],
        maximo: int,
        digitos_iniciais: str,
        prefixo: str | None,
        ao_mudar: Callable[[], None] | None,
    ) -> None:
        self._aplicar = aplicar
        self._maximo = maximo
        self._ao_mudar_externo = ao_mudar
        self.mascarado = aplicar(digitos_iniciais)
        self.controle = basicos.campo_texto(
            rotulo,
            value=self.mascarado.texto,
            prefix=prefixo,
            keyboard_type=ft.KeyboardType.NUMBER,
            autocorrect=False,
            enable_suggestions=False,
            text_align=ft.TextAlign.RIGHT,
            on_change=self._ao_mudar,
            on_focus=self._ao_focar,
            on_click=self._ao_focar,
        )

    @property
    def valor(self):
        """Valor para o serviço, ou None enquanto a máscara indicar erro."""
        return self.mascarado.valor

    @property
    def erro(self) -> str | None:
        return self.mascarado.erro

    def _cursor_no_fim(self) -> None:
        fim = len(self.controle.value or "")
        self.controle.selection = ft.TextSelection(base_offset=fim, extent_offset=fim)

    def _ao_focar(self, _e=None) -> None:
        """Ao tocar no campo, o cursor vai para o fim: o backspace apaga o último dígito."""
        self._cursor_no_fim()
        self.controle.update()

    def _ao_mudar(self, _e=None) -> None:
        digitos = mascaras.editar_digitos(
            self.mascarado.digitos, self.mascarado.texto, self.controle.value or "", self._maximo
        )
        resultado = self._aplicar(digitos)
        self.mascarado = resultado
        # Sempre reescreve e põe o cursor no fim: o próximo dígito entra pela direita
        # mesmo que o usuário tenha tocado no meio do número.
        self.controle.value = resultado.texto
        self._cursor_no_fim()
        self.controle.error = resultado.erro
        self.controle.update()
        if self._ao_mudar_externo:
            self._ao_mudar_externo()

    def marcar_erro(self, mensagem: str | None) -> None:
        self.controle.error = mensagem


class CampoDinheiro(_CampoMascarado):
    """R$ com dígitos entrando pela direita. ``valor``: centavos (int)."""

    def __init__(self, rotulo: str, centavos: int = 0, ao_mudar=None) -> None:
        super().__init__(
            rotulo,
            mascaras.mascara_dinheiro,
            mascaras.DIGITOS_MAX_DINHEIRO,
            mascaras.digitos_de_centavos(centavos),
            "R$ ",
            ao_mudar,
        )


class CampoDuracao(_CampoMascarado):
    """H:MM, horas até 999. ``valor``: minutos (int)."""

    def __init__(self, rotulo: str, minutos: int = 0, ao_mudar=None) -> None:
        super().__init__(
            rotulo,
            lambda t: mascaras.mascara_hora(t, mascaras.DURACAO),
            mascaras.DIGITOS_MAX_DURACAO,
            mascaras.digitos_de_minutos(minutos),
            None,
            ao_mudar,
        )


class CampoHora(_CampoMascarado):
    """HH:MM de 00:00 a 23:59. ``valor``: datetime.time."""

    def __init__(self, rotulo: str, hora: time | None = None, ao_mudar=None) -> None:
        super().__init__(
            rotulo,
            lambda t: mascaras.mascara_hora(t, mascaras.RELOGIO),
            mascaras.DIGITOS_MAX_RELOGIO,
            mascaras.digitos_de_hora(hora) if hora else "",
            None,
            ao_mudar,
        )
