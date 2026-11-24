"""Notificações por e-mail (prompt 32): a seção do Perfil e a tela 'Fila de e-mails'.

Quem decide é services/notificacoes.py e services/fila_email.py: o papel usuario é
recusado lá; esconder a seção aqui é só conveniência.
"""

from __future__ import annotations

import flet as ft

from osapp import formatacao
from osapp.services import fila_email, notificacoes
from osapp.services.erros import ErroPermissao
from osapp.ui import theme
from osapp.ui.components import basicos
from osapp.ui.components.chips import GrupoChips
from osapp.ui.components.secao import SecaoCard, status_pill
from osapp.ui.views.base import Tela

TITULO_SECAO = "Notificações por e-mail"
EXPLICACAO = (
    "Opcional. O e-mail só é usado para avisar de novas solicitações das suas filiais. "
    "Você pode removê-lo quando quiser."
)
ROTULO_EMAIL = "E-mail"
ROTULO_CODIGO = "Código de 6 números"
ROTULO_ENVIAR_CODIGO = "Enviar código"
ROTULO_CONFIRMAR = "Confirmar"
ROTULO_RECEBER = "Receber notificações"
ROTULO_URGENCIA_MINIMA = "Urgência mínima"
ROTULO_REMOVER = "Remover e-mail"
NAO_CONFIRMADO = "Não confirmado"
SEM_EMAIL = "Nenhum e-mail cadastrado"
AVISO_CODIGO = "Enviamos um código para o seu e-mail. Ele vale por 15 minutos."
AVISO_CONFIRMADO = "E-mail confirmado."
AVISO_REMOVIDO = "E-mail removido."

OPCOES_URGENCIA_MINIMA = (
    ("baixa", "Todas"),
    ("alta", "Alta e acima"),
    ("emergencial", "Somente emergencial"),
)

TITULO_FILA = "Fila de e-mails"
ROTULOS_STATUS_FILA = {
    "pendente": "Pendentes",
    "enviando": "Enviando",
    "enviado": "Enviados",
    "falhou": "Falharam",
    "cancelado": "Cancelados",
}
ROTULOS_TIPO = {"nova_solicitacao": "Nova solicitação", "codigo_confirmacao": "Código"}


def texto_status(confirmado_em, email: str | None) -> str:
    """'Confirmado em 24/11/2026', 'Não confirmado' ou 'Nenhum e-mail cadastrado'.
    Função pura (testada)."""
    if not email:
        return SEM_EMAIL
    if confirmado_em is None:
        return NAO_CONFIRMADO
    return f"Confirmado em {formatacao.formatar_data(confirmado_em)}"


def _atualizar(controle) -> None:
    try:
        controle.update()
    except RuntimeError:
        pass  # ainda não está na página, ou a tela foi trocada


class SecaoEmail:
    """Seção do Perfil (manutenção e administrador). ``controle`` é o cartão."""

    def __init__(self, app) -> None:
        self.app = app
        self.estado: notificacoes.MinhasNotificacoes | None = None
        self.email = basicos.campo_texto(
            ROTULO_EMAIL,
            keyboard_type=ft.KeyboardType.EMAIL,
            max_length=notificacoes.email_mensagem.EMAIL_MAX,
        )
        self.codigo = basicos.campo_texto(
            ROTULO_CODIGO,
            keyboard_type=ft.KeyboardType.NUMBER,
            max_length=notificacoes.CODIGO_DIGITOS,
            on_submit=self._confirmar,
        )
        self.situacao = basicos.rotulo_valor("Situação", NAO_CONFIRMADO)
        self.receber = ft.Switch(
            label=ROTULO_RECEBER,
            value=False,
            active_color=theme.COR_BOTAO_PRIMARIO,
            label_text_style=ft.TextStyle(color=theme.COR_TITULO, size=theme.FONTE_CORPO),
            on_change=self._ao_mudar_receber,
        )
        self.urgencia = GrupoChips(
            OPCOES_URGENCIA_MINIMA, "baixa", opcional=False, ao_mudar=self._ao_mudar_urgencia
        )
        self.botao_codigo = basicos.botao_primario(
            ROTULO_ENVIAR_CODIGO, ft.Icons.SEND_OUTLINED, self._enviar_codigo
        )
        self.botao_confirmar = basicos.botao_secundario(
            ROTULO_CONFIRMAR, ft.Icons.CHECK, self._confirmar
        )
        self.bloco_codigo = basicos.coluna([self.codigo, self.botao_confirmar])
        self.botao_remover = basicos.botao_secundario(
            ROTULO_REMOVER, ft.Icons.DELETE_OUTLINE, self._perguntar_remover
        )
        self.campos = {"email": self.email, "codigo": self.codigo}
        self.secao = SecaoCard(
            None,
            ft.Icons.MAIL_OUTLINE,
            TITULO_SECAO,
            [
                basicos.subtitulo(EXPLICACAO),
                self.email,
                self.botao_codigo,
                self.bloco_codigo,
                self.situacao,
                self.receber,
                basicos.subtitulo(ROTULO_URGENCIA_MINIMA),
                self.urgencia.controle,
                self.botao_remover,
            ],
        )
        self.controle = self.secao.controle
        self._mostrar(None)

    # --- Estado -> tela ----------------------------------------------------------------

    def _mostrar(self, estado: notificacoes.MinhasNotificacoes | None) -> None:
        self.estado = estado
        email = estado.email if estado else None
        confirmado = estado is not None and estado.confirmado_em is not None and bool(email)
        self.email.value = email or ""
        self.situacao.controls[1].value = texto_status(
            estado.confirmado_em if estado else None, email
        )
        self.bloco_codigo.visible = bool(estado and estado.codigo_pendente)
        self.receber.value = bool(estado and estado.notificacoes_ativas)
        self.receber.disabled = not confirmado
        self.urgencia.definir(estado.urgencia_minima if estado else "baixa")
        self.botao_remover.visible = bool(email)
        if confirmado:
            pill = status_pill("Confirmado", "sucesso")
        elif email:
            pill = status_pill(NAO_CONFIRMADO, "alerta")
        else:
            pill = None
        self.secao.definir_pill(pill)
        _atualizar(self.controle)

    async def carregar(self) -> None:
        resultado = await self.app.chamar(
            notificacoes.obter_minhas, self.app.sessao.ator_id, erros_tratados=(ErroPermissao,)
        )
        if resultado.ok:
            self._mostrar(resultado.valor)

    # --- Ações --------------------------------------------------------------------------

    async def _enviar_codigo(self, _e=None) -> None:
        if self.botao_codigo.disabled:
            return
        self.email.error = None
        self.botao_codigo.disabled = True
        _atualizar(self.controle)
        try:
            resultado = await self.app.chamar(
                notificacoes.enviar_codigo,
                self.app.sessao.ator_id,
                self.email.value or "",
                campos=self.campos,
            )
        finally:
            self.botao_codigo.disabled = False
            _atualizar(self.controle)
        if resultado.ok:
            self.codigo.value = ""
            self._mostrar(resultado.valor)
            self.app.avisar(AVISO_CODIGO)

    async def _confirmar(self, _e=None) -> None:
        self.codigo.error = None
        resultado = await self.app.chamar(
            notificacoes.confirmar_codigo,
            self.app.sessao.ator_id,
            self.codigo.value or "",
            campos=self.campos,
        )
        if resultado.ok:
            self.codigo.value = ""
            self._mostrar(resultado.valor)
            self.app.avisar(AVISO_CONFIRMADO)
        else:
            await self.carregar()  # o código pode ter sido bloqueado

    async def _ao_mudar_receber(self, _e=None) -> None:
        resultado = await self.app.chamar(
            notificacoes.definir_notificacoes, self.app.sessao.ator_id, bool(self.receber.value)
        )
        if resultado.ok:
            self._mostrar(resultado.valor)
        else:
            await self.carregar()

    def _ao_mudar_urgencia(self) -> None:
        self.app.page.run_task(self._gravar_urgencia)

    async def _gravar_urgencia(self) -> None:
        resultado = await self.app.chamar(
            notificacoes.definir_urgencia_minima, self.app.sessao.ator_id, self.urgencia.valor
        )
        if resultado.ok:
            self._mostrar(resultado.valor)

    def _perguntar_remover(self, _e=None) -> None:
        self.app.confirmar(
            "Remover e-mail?",
            "O endereço é apagado e você deixa de receber notificações.",
            "Remover",
            self._remover,
        )

    async def _remover(self) -> None:
        resultado = await self.app.chamar(notificacoes.remover_email, self.app.sessao.ator_id)
        if resultado.ok:
            self._mostrar(resultado.valor)
            self.app.avisar(AVISO_REMOVIDO)


class FilaEmails(Tela):
    """Só administrador: contagem por status, últimos erros (sem corpo, endereço
    mascarado) e 'Reenviar' de uma linha que falhou."""

    def __init__(self, app, **_params) -> None:
        self.app = app
        self.conteudo = basicos.coluna([basicos.carregando()])

    async def carregar(self) -> None:
        resultado = await self.app.chamar(
            fila_email.resumo_fila, self.app.sessao.ator_id, erros_tratados=(ErroPermissao,)
        )
        if not resultado.ok:
            self.conteudo.controls = [basicos.mensagem_central(self.app.MENSAGEM_GENERICA)]
            _atualizar(self.conteudo)
            return
        r = resultado.valor
        contagens = [
            basicos.rotulo_valor(rotulo, str(r.contagens.get(status, 0)), uma_linha=True)
            for status, rotulo in ROTULOS_STATUS_FILA.items()
        ]
        controles: list[ft.Control] = [
            basicos.titulo(TITULO_FILA, theme.FONTE_SAUDACAO),
            basicos.cartao(
                basicos.coluna(
                    [
                        basicos.titulo("Mensagens"),
                        ft.Row(contagens, wrap=True, spacing=theme.ESPACO_G),
                        basicos.subtitulo(
                            "Envio configurado."
                            if r.configurado
                            else "Envio não configurado: as mensagens ficam pendentes."
                        ),
                    ]
                )
            ),
            basicos.titulo("Últimos erros"),
        ]
        controles += [self._cartao_erro(e) for e in r.erros] or [
            basicos.mensagem_central("Nenhum erro registrado.")
        ]
        self.conteudo.controls = controles
        _atualizar(self.conteudo)

    def _cartao_erro(self, e) -> ft.Control:
        linhas: list[ft.Control] = [
            ft.Text(
                f"#{e.id}  ·  {ROTULOS_TIPO.get(e.tipo, e.tipo)}  ·  {e.destino}",
                color=theme.COR_TITULO,
                size=theme.FONTE_CORPO,
                weight=ft.FontWeight.BOLD,
            ),
            basicos.subtitulo(
                f"{formatacao.formatar_data_hora(e.criado_em)}  ·  "
                f"{ROTULOS_STATUS_FILA.get(e.status, e.status)}  ·  "
                f"{e.tentativas} tentativa(s)"
            ),
            basicos.texto(e.erro),
        ]
        if e.pode_reenviar:

            async def reenviar(_e=None, linha_id=e.id) -> None:
                resultado = await self.app.chamar(
                    fila_email.reenviar, self.app.sessao.ator_id, linha_id
                )
                if resultado.ok:
                    self.app.avisar("Mensagem colocada de novo na fila.")
                    await self.carregar()

            linhas.append(basicos.botao_secundario("Reenviar", ft.Icons.REPLAY, reenviar))
        return basicos.cartao(basicos.coluna(linhas, espaco=4))
