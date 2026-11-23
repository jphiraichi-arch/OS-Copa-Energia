"""Seletor do escopo da busca (prompt 22): 'Itens' ou 'Tudo'.

Padrão por tela (decisão de 21/11/2026): Home 'Tudo'; relatório 'Itens'.

Só para manutenção e administrador; quem decide o escopo efetivo é o serviço
(ordens.condicao_busca), que sempre busca só em título e descrição para o papel usuario.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from osapp.services import ordens
from osapp.ui.components.chips import GrupoChips

ROTULOS = {ordens.ESCOPO_ITENS: "Itens", ordens.ESCOPO_TUDO: "Tudo"}


class SeletorEscopo:
    """Dois chips de escolha única (GrupoChips): 'Itens' e 'Tudo'."""

    def __init__(
        self, app, ao_mudar: Callable[[], Awaitable[None]], inicial: str = ordens.ESCOPO_ITENS
    ) -> None:
        if inicial not in ordens.ESCOPOS:
            raise ValueError(f"Escopo desconhecido: {inicial!r}")
        self.app = app
        self._ao_mudar = ao_mudar
        self.grupo = GrupoChips(
            list(ROTULOS.items()),
            inicial,
            opcional=False,
            ao_mudar=lambda: app.page.run_task(self._ao_mudar),
        )
        self.controle = self.grupo.controle

    @property
    def valor(self) -> str:
        return self.grupo.valor
