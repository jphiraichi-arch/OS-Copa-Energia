"""Seções numeradas dos formulários e o rótulo de situação (StatusPill).

SecaoCard: cartão branco arredondado. Cabeçalho: ícone + '1. TÍTULO DA SEÇÃO' em
maiúsculas, um asterisco quando obrigatória e, à direita, um StatusPill opcional.
"""

from __future__ import annotations

import flet as ft

from osapp.ui import theme

# Tons do StatusPill -> (fundo, texto). O texto sempre aparece (a cor nunca é o único sinal).
TONS = {
    "neutro": theme.COR_STATUS_OUTRO,
    "info": theme.COR_STATUS_ABERTA,
    "alerta": theme.COR_STATUS_EM_EXECUCAO,
    "sucesso": theme.COR_STATUS_CONCLUIDA,
    "baixa": theme.COR_NIVEL_BAIXA,
    "media": theme.COR_NIVEL_MEDIA,
    "alta": theme.COR_NIVEL_ALTA,
    "emergencial": theme.COR_NIVEL_EMERGENCIAL,
}


def status_pill(texto: str, tom: str = "neutro") -> ft.Container:
    """Rótulo pequeno e arredondado, por exemplo 'URGÊNCIA: ALTA'."""
    fundo, cor = TONS.get(tom, TONS["neutro"])
    return ft.Container(
        bgcolor=fundo,
        border_radius=theme.RAIO_CHIP,
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        content=ft.Text(
            texto.upper(), color=cor, size=theme.FONTE_PEQUENA, weight=ft.FontWeight.BOLD
        ),
    )


def titulo_secao(numero: int | None, titulo: str, obrigatoria: bool = False) -> str:
    """'1. SOLICITAÇÃO *' (função pura, para teste)."""
    prefixo = f"{numero}. " if numero is not None else ""
    return f"{prefixo}{titulo.upper()}{' *' if obrigatoria else ''}"


class SecaoCard:
    """Uma seção do formulário. ``pill`` pode ser trocado depois com ``definir_pill``."""

    def __init__(
        self,
        numero: int | None,
        icone: ft.IconData,
        titulo: str,
        conteudo: list[ft.Control],
        obrigatoria: bool = False,
        pill: ft.Control | None = None,
    ) -> None:
        self._lugar_pill = ft.Container(content=pill)
        self.corpo = ft.Column(
            conteudo, spacing=theme.ESPACO_M, horizontal_alignment=ft.CrossAxisAlignment.STRETCH
        )
        self.controle = ft.Container(
            bgcolor=theme.COR_CARTAO,
            border_radius=theme.RAIO_CARTAO,
            padding=theme.ESPACO_M,
            shadow=ft.BoxShadow(blur_radius=12, color=theme.COR_SOMBRA, offset=ft.Offset(0, 2)),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icone, color=theme.COR_DESTAQUE),
                            ft.Text(
                                titulo_secao(numero, titulo, obrigatoria),
                                color=theme.COR_TITULO,
                                size=theme.FONTE_CORPO,
                                weight=ft.FontWeight.BOLD,
                                expand=True,
                            ),
                            self._lugar_pill,
                        ],
                        spacing=theme.ESPACO_P,
                        wrap=False,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.corpo,
                ],
                spacing=theme.ESPACO_M,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
        )

    def definir_pill(self, pill: ft.Control | None) -> None:
        self._lugar_pill.content = pill
        try:
            self._lugar_pill.update()
        except RuntimeError:
            pass  # ainda não está na página


def secao(numero, icone, titulo, conteudo, obrigatoria=False, pill=None) -> ft.Control:
    """Atalho para quando a seção não muda depois de montada."""
    return SecaoCard(numero, icone, titulo, conteudo, obrigatoria, pill).controle
