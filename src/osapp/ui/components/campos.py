"""Campos de dinheiro, duração e hora do relógio, sem máscara ao vivo.

O valor do campo nunca é reescrito em ``on_change``: em 4G lento, reescrever o texto a
cada tecla perdia dígitos. O texto é formatado quando o campo perde o foco
(``on_blur``) e lido ao gravar (``valor``/``erro``), com as funções puras de
ui/leitura.py. A validação que vale é a do serviço.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import time

import flet as ft

from osapp.ui import leitura
from osapp.ui.components import basicos


class _CampoFormatado:
    def __init__(
        self,
        rotulo: str,
        ler: Callable[[object], leitura.Lido],
        texto_inicial: str,
        prefixo: str | None,
        dica: str,
        ao_mudar: Callable[[], None] | None,
    ) -> None:
        self._ler = ler
        self._ao_mudar_externo = ao_mudar
        self.controle = basicos.campo_texto(
            rotulo,
            value=texto_inicial,
            prefix=prefixo,
            hint_text=dica,
            keyboard_type=ft.KeyboardType.NUMBER,
            autocorrect=False,
            enable_suggestions=False,
            text_align=ft.TextAlign.RIGHT,
            on_change=self._ao_mudar,
            on_blur=self._ao_sair,
        )

    @property
    def lido(self) -> leitura.Lido:
        return self._ler(self.controle.value)

    @property
    def valor(self):
        """Valor para o serviço, ou None enquanto o texto não for válido."""
        return self.lido.valor

    @property
    def erro(self) -> str | None:
        return self.lido.erro

    def _ao_mudar(self, _e=None) -> None:
        # Nunca reescreve o valor aqui: só tira a mensagem de erro, se houver, e avisa
        # a tela (prévias de totais e de tempo).
        if self.controle.error:
            self.controle.error = None
            self.controle.update()
        if self._ao_mudar_externo:
            self._ao_mudar_externo()

    def _ao_sair(self, _e=None) -> None:
        """Ao perder o foco: mostra o texto formatado, ou o erro (o texto fica como está)."""
        lido = self.lido
        if lido.erro:
            self.controle.error = lido.erro
        else:
            self.controle.error = None
            self.controle.value = lido.texto
        self.controle.update()
        if self._ao_mudar_externo:
            self._ao_mudar_externo()

    def marcar_erro(self, mensagem: str | None) -> None:
        self.controle.error = mensagem


class CampoDinheiro(_CampoFormatado):
    """R$; '150' = R$ 150,00. ``valor``: centavos (int)."""

    def __init__(self, rotulo: str, centavos: int = 0, ao_mudar=None) -> None:
        super().__init__(
            rotulo,
            leitura.ler_dinheiro,
            leitura.texto_dinheiro(centavos),
            "R$ ",
            "0,00",
            ao_mudar,
        )


class CampoDuracao(_CampoFormatado):
    """H:MM, horas até 999. ``valor``: minutos (int); vazio = 0."""

    def __init__(self, rotulo: str, minutos: int = 0, ao_mudar=None) -> None:
        super().__init__(
            rotulo,
            leitura.ler_duracao,
            leitura.texto_duracao(minutos),
            None,
            "0:00",
            ao_mudar,
        )


class CampoHora(_CampoFormatado):
    """HH:MM de 00:00 a 23:59. ``valor``: datetime.time."""

    def __init__(self, rotulo: str, hora: time | None = None, ao_mudar=None) -> None:
        super().__init__(
            rotulo,
            leitura.ler_hora,
            leitura.texto_hora(hora),
            None,
            "HH:MM",
            ao_mudar,
        )
