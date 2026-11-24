"""Perfil > SLA (prompt 38, só administrador): uma tabela por filial; linhas = urgência,
colunas = início e solução, digitadas em horas com a máscara de duração (H:MM; um dia =
24:00). Quem decide e registra no log é services/sla.py."""

from __future__ import annotations

import flet as ft

from osapp.services import sla
from osapp.services.erros import ErroPermissao
from osapp.ui import theme
from osapp.ui.components import basicos
from osapp.ui.components.campos import CampoDuracao
from osapp.ui.components.secao import SecaoCard
from osapp.ui.views.base import Tela

TITULO = "SLA"
AJUDA = (
    "Prazos em horas de relógio (um dia = 24:00). Valem para as ordens abertas depois da "
    "mudança; as ordens que já existem mantêm os prazos que tinham."
)


def em_dias(minutos: int) -> str:
    """'= 2 dias', '= 1 dia e 12 h', '' (menos de um dia). Função pura (testada)."""
    if minutos < sla.DIA:
        return ""
    dias, resto = divmod(minutos, sla.DIA)
    texto = f"= {dias} dia{'s' if dias > 1 else ''}"
    return texto + (f" e {resto // 60} h" if resto >= 60 else "")


def _atualizar(controle) -> None:
    try:
        controle.update()
    except RuntimeError:
        pass


class Sla(Tela):
    def __init__(self, app, **_params) -> None:
        self.app = app
        self.lista = basicos.coluna([basicos.carregando()])
        self.conteudo = basicos.coluna(
            [basicos.titulo(TITULO, theme.FONTE_SAUDACAO), basicos.subtitulo(AJUDA), self.lista]
        )

    async def carregar(self) -> None:
        r = await self.app.chamar(
            sla.listar_alvos, self.app.sessao.ator_id, erros_tratados=(ErroPermissao,)
        )
        if not r.ok:
            self.conteudo.controls = [basicos.mensagem_central(self.app.MENSAGEM_GENERICA)]
        else:
            self.lista.controls = [self._filial(f) for f in r.valor]
        _atualizar(self.conteudo)

    def _filial(self, f) -> ft.Control:
        return SecaoCard(
            None,
            ft.Icons.TIMER_OUTLINED,
            f"{f.filial_codigo} - {f.filial_nome}",
            [self._linha(f.filial_id, a) for a in f.alvos],
        ).controle

    def _linha(self, filial_id: int, a) -> ft.Control:
        inicio = CampoDuracao("Início (H:MM)", a.prazo_inicio_min)
        solucao = CampoDuracao("Solução (H:MM)", a.prazo_solucao_min)
        dias = basicos.subtitulo(
            f"Início {em_dias(a.prazo_inicio_min) or ''}  ·  "
            f"Solução {em_dias(a.prazo_solucao_min) or ''}".strip()
        )

        async def salvar(_e=None) -> None:
            if inicio.erro or solucao.erro:
                return
            r = await self.app.chamar(
                sla.definir_alvo,
                self.app.sessao.ator_id,
                filial_id,
                a.urgencia,
                inicio.valor,
                solucao.valor,
                campos={
                    "prazo_inicio_min": inicio.controle,
                    "prazo_solucao_min": solucao.controle,
                },
            )
            if r.ok:
                self.app.avisar("Prazo salvo. Vale para as próximas ordens.")
                await self.carregar()

        return basicos.coluna(
            [
                ft.Row([basicos.selo_nivel(a.urgencia)]),
                ft.ResponsiveRow(
                    [
                        ft.Container(col={"xs": 12, "sm": 5}, content=inicio.controle),
                        ft.Container(col={"xs": 12, "sm": 5}, content=solucao.controle),
                        ft.Container(
                            col={"xs": 12, "sm": 2},
                            content=ft.TextButton(
                                content="Salvar",
                                style=theme.estilo_botao_texto(),
                                height=theme.ALVO_TOQUE_MIN,
                                on_click=salvar,
                            ),
                        ),
                    ],
                    spacing=theme.ESPACO_P,
                    run_spacing=theme.ESPACO_P,
                ),
                dias,
                ft.Divider(height=1, thickness=1, color=theme.COR_CONTORNO),
            ],
            espaco=theme.ESPACO_P,
        )
