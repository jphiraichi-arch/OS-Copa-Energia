"""Gestão de usuários (só administrador): /usuarios, /usuarios/novo e /usuarios/{id}.

Quem decide é services/usuarios.py; para os outros papéis o serviço recusa e a tela
mostra a mensagem genérica.
"""

from __future__ import annotations

import flet as ft

from osapp import formatacao
from osapp.services import especialidades, notificacoes, ordens, sessoes_lembradas, usuarios
from osapp.services.auth import PAPEIS
from osapp.services.erros import ErroConflito, ErroNaoEncontrado, ErroPermissao
from osapp.ui import rotas, rotulos, theme
from osapp.ui.components import basicos
from osapp.ui.components.chips import GrupoChips
from osapp.ui.components.formulario_os import lista_suspensa
from osapp.ui.views.base import Tela
from osapp.ui.views.notificacoes_email import SEM_EMAIL, TITULO_SECAO
from osapp.ui.views.notificacoes_email import texto_status as texto_status_email

TODOS = "todos"
MSG_CONFLITO = "Este usuário foi alterado por outra pessoa. Abra de novo e tente outra vez."
MSG_LOGIN_EXISTE = "Já existe um usuário com este login."
ROTULO_SENHA_TEMPORARIA = "Senha temporária"
AJUDA_SENHA_TEMPORARIA = "O usuário vai trocar esta senha no primeiro acesso."
ROTULO_FILIAIS = "Filiais permitidas"
ROTULO_FILIAL_PADRAO = "Filial padrão"
ROTULO_ESPECIALIDADES = "Especialidades (só para manutenção)"
AVISO_SENHA_UMA_VEZ = (
    "Anote e entregue ao usuário. Ela não será mostrada de novo; o usuário vai "
    "trocá-la no primeiro acesso."
)
TEXTO_REDEFINIR = (
    "O sistema vai gerar uma senha temporária nova e mostrá-la uma única vez. A senha "
    "atual deixa de valer e o usuário sai dos aparelhos lembrados."
)


def texto_filiais(codigos, padrao: str) -> str:
    """'1007 (padrão), 2001'. Função pura (testada)."""
    return ", ".join(f"{c} (padrão)" if c == padrao else c for c in codigos)


def _mensagem(tela, texto: str, rota: str, rotulo: str) -> None:
    async def voltar(_e=None) -> None:
        await tela.app.ir(rota)

    tela.conteudo.controls = [
        basicos.mensagem_central(texto),
        basicos.botao_secundario(rotulo, ft.Icons.ARROW_BACK, voltar),
    ]


def _atualizar(controle) -> None:
    try:
        controle.update()
    except RuntimeError:
        pass  # a tela já foi trocada


class ListaUsuarios(Tela):
    def __init__(self, app, **_params) -> None:
        self.app = app
        self.busca = basicos.campo_texto(
            "Buscar por nome ou login", on_submit=self._recarregar, expand=True
        )
        self.papel = lista_suspensa(
            "Papel",
            [
                ft.DropdownOption(key=TODOS, text="Todos"),
                *[ft.DropdownOption(key=p, text=rotulos.papel(p)) for p in PAPEIS],
            ],
            TODOS,
            on_select=self._recarregar,
        )
        self.situacao = lista_suspensa(
            "Situação",
            [
                ft.DropdownOption(key=TODOS, text="Todos"),
                ft.DropdownOption(key="ativos", text="Ativos"),
                ft.DropdownOption(key="inativos", text="Inativos"),
            ],
            "ativos",
            on_select=self._recarregar,
        )
        self.filial = lista_suspensa(
            "Filial",
            [ft.DropdownOption(key=TODOS, text="Todas")],
            TODOS,
            on_select=self._recarregar,
        )
        self.lista = basicos.coluna([basicos.carregando()], espaco=theme.ESPACO_P + 4)
        self.conteudo = basicos.coluna(
            [
                basicos.titulo("Usuários", theme.FONTE_SAUDACAO),
                basicos.botao_primario("Novo usuário", ft.Icons.PERSON_ADD_ALT, self._novo),
                ft.Row(
                    [
                        self.busca,
                        ft.IconButton(
                            icon=ft.Icons.SEARCH,
                            icon_color=theme.COR_BOTAO_PRIMARIO,
                            tooltip="Buscar",
                            on_click=self._recarregar,
                        ),
                    ]
                ),
                ft.ResponsiveRow(
                    [
                        ft.Container(col={"xs": 12, "sm": 4}, content=ft.Row([campo]))
                        for campo in (self.papel, self.filial, self.situacao)
                    ],
                    spacing=theme.ESPACO_P,
                    run_spacing=theme.ESPACO_P,
                ),
                self.lista,
            ]
        )

    async def _novo(self, _e=None) -> None:
        await self.app.ir(rotas.USUARIO_NOVO)

    async def carregar(self) -> None:
        filiais = await self.app.chamar(ordens.listar_filiais, self.app.sessao.ator_id)
        if filiais.ok:
            self.filial.options = [
                ft.DropdownOption(key=TODOS, text="Todas"),
                *[
                    ft.DropdownOption(key=str(f.id), text=f"{f.codigo} - {f.nome}")
                    for f in filiais.valor
                ],
            ]
        await self._recarregar()

    async def _recarregar(self, _e=None) -> None:
        situacao = self.situacao.value
        resultado = await self.app.chamar(
            usuarios.listar_usuarios,
            self.app.sessao.ator_id,
            self.busca.value or None,
            None if self.papel.value == TODOS else self.papel.value,
            None if self.filial.value in (None, TODOS) else int(self.filial.value),
            None if situacao == TODOS else situacao == "ativos",
            erros_tratados=(ErroPermissao,),
        )
        if isinstance(resultado.erro, ErroPermissao):
            _mensagem(self, self.app.MENSAGEM_GENERICA, rotas.HOME, "Voltar para a lista")
        elif resultado.ok:
            self.lista.controls = [self._cartao(u) for u in resultado.valor] or [
                basicos.mensagem_central("Nenhum usuário encontrado.")
            ]
        _atualizar(self.conteudo)

    def _cartao(self, u) -> ft.Control:
        filiais_txt = texto_filiais(u.filiais_codigos or (u.filial_codigo,), u.filial_codigo)
        selos = [basicos.selo(rotulos.papel(u.papel), *theme.COR_ORIGEM)]
        if not u.ativo:
            selos.append(basicos.selo("Inativo", *theme.COR_STATUS_CANCELADA))
        if u.deve_trocar_senha:
            selos.append(basicos.selo("Senha temporária", *theme.COR_NIVEL_MEDIA))
        return basicos.cartao(
            ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(
                                u.nome,
                                color=theme.COR_TITULO,
                                size=theme.FONTE_CORPO,
                                weight=ft.FontWeight.BOLD,
                            ),
                            basicos.subtitulo(f"{u.login}  ·  {filiais_txt}"),
                            *(
                                [
                                    basicos.subtitulo(
                                        f"{u.email}"
                                        f"{'' if u.email_confirmado else ' (não confirmado)'}"
                                    )
                                ]
                                if u.email
                                else []
                            ),
                            ft.Row(selos, wrap=True, spacing=6, run_spacing=6),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=theme.COR_SUBTITULO),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            on_click=lambda _e, i=u.id: self.app.page.run_task(self.app.ir, rotas.rota_usuario(i)),
        )


class FormularioUsuario(Tela):
    """Criar (sem ``usuario_id``) ou alterar um usuário."""

    def __init__(self, app, usuario_id: int | None = None, **_params) -> None:
        self.app = app
        self.usuario_id = usuario_id
        self.usuario = None
        self.aviso = ft.Text("", color=theme.COR_ERRO, size=theme.FONTE_SUBTITULO, visible=False)
        self.conteudo = basicos.coluna([basicos.carregando()])
        self._inicial: tuple | None = None

    def tem_alteracoes(self) -> bool:
        return self._inicial is not None and self._digitado() != self._inicial

    def _digitado(self) -> tuple:
        login = self.login.value if self.usuario is None else ""
        filiais = tuple(sorted(self.filiais.valor))
        esp = tuple(sorted(self.especialidades.valor))
        return (self.nome.value, login, self.filial.value, self.papel.value, filiais, esp)

    async def carregar(self) -> None:
        ator_id = self.app.sessao.ator_id
        if self.usuario_id is not None:
            resultado = await self.app.chamar(
                usuarios.obter_usuario,
                ator_id,
                self.usuario_id,
                erros_tratados=(ErroPermissao, ErroNaoEncontrado),
            )
            if isinstance(resultado.erro, ErroNaoEncontrado):
                _mensagem(self, "Usuário não encontrado.", rotas.USUARIOS, "Voltar")
                _atualizar(self.conteudo)
                return
            if not resultado.ok:
                _mensagem(self, self.app.MENSAGEM_GENERICA, rotas.HOME, "Voltar para a lista")
                _atualizar(self.conteudo)
                return
            self.usuario = resultado.valor
        else:
            # Só para o serviço recusar quem não é administrador antes de mostrar o form.
            teste = await self.app.chamar(
                usuarios.listar_usuarios,
                ator_id,
                "",
                None,
                None,
                True,
                erros_tratados=(ErroPermissao,),
            )
            if not teste.ok:
                _mensagem(self, self.app.MENSAGEM_GENERICA, rotas.HOME, "Voltar para a lista")
                _atualizar(self.conteudo)
                return
        filiais = await self.app.chamar(ordens.listar_filiais, ator_id)
        if not filiais.ok:
            return
        await self._montar(filiais.valor)
        _atualizar(self.conteudo)

    async def _montar(self, filiais) -> None:
        u = self.usuario
        self.nome = basicos.campo_texto(
            "Nome", value=u.nome if u else "", max_length=usuarios.NOME_MAX
        )
        self.login = basicos.campo_texto(
            "Login", value=u.login if u else "", read_only=u is not None, max_length=50
        )
        padrao = u.filial_id if u else self.app.sessao.filial_id
        self.filial = lista_suspensa(
            ROTULO_FILIAL_PADRAO,
            [ft.DropdownOption(key=str(f.id), text=f"{f.codigo} - {f.nome}") for f in filiais],
            str(padrao),
            on_select=self._ao_mudar_padrao,
        )
        self.filiais = GrupoChips(
            [(f.id, f.codigo) for f in filiais],
            set(u.filiais) if u and u.filiais else {padrao},
            multipla=True,
            minimo=1,
        )
        self.papel = lista_suspensa(
            "Papel",
            [ft.DropdownOption(key=p, text=rotulos.papel(p)) for p in PAPEIS],
            u.papel if u else "usuario",
        )
        # Prompt 37: especialidades (só manutenção; o serviço recusa para outros papéis).
        lista_esp = await self.app.chamar(especialidades.listar, self.app.sessao.ator_id)
        self.especialidades = GrupoChips(
            [(e.id, e.nome) for e in (lista_esp.valor if lista_esp.ok else [])],
            set(u.especialidades) if u else set(),
            multipla=True,
        )
        self.campos = {
            "especialidades": self.especialidades,
            "nome": self.nome,
            "login": self.login,
            "filial_id": _ErroNaLista(self.filial),
            "filiais": self.filiais,
            "papel": _ErroNaLista(self.papel),
            "ativo": self,
        }
        self.botao = basicos.botao_primario(
            "Criar usuário" if u is None else "Salvar alterações", ft.Icons.SAVE, self._salvar
        )
        campos: list[ft.Control] = [
            self.nome,
            self.login,
            ft.Row([self.papel]),
            basicos.subtitulo(ROTULO_FILIAIS),
            self.filiais.controle,
            ft.Row([self.filial]),
        ]
        if u is not None:
            campos += [basicos.subtitulo(ROTULO_ESPECIALIDADES), self.especialidades.controle]
        if u is None:
            campos.append(basicos.subtitulo(f"{AJUDA_SENHA_TEMPORARIA} Ela é gerada ao criar."))
        cartoes: list[ft.Control] = [
            basicos.cartao(
                basicos.coluna(
                    [
                        basicos.titulo("Novo usuário" if u is None else "Alterar usuário"),
                        *campos,
                        self.aviso,
                    ]
                )
            ),
            self.botao,
        ]
        if u is not None:
            cartoes.append(self._acoes(u))
            cartoes.append(await self._notificacoes())
            cartoes.append(await self._historico())
        self.conteudo.controls = cartoes
        self._inicial = self._digitado()

    def _ao_mudar_padrao(self, _e=None) -> None:
        """A filial padrão entra sempre nas permitidas."""
        if self.filial.value:
            self.filiais.valor.add(int(self.filial.value))
            self.filiais.definir(self.filiais.valor)
            self.filiais.update()

    # O ErroValidacao de 'ativo' (último administrador) aparece no aviso da tela.
    @property
    def error(self) -> str | None:
        return self.aviso.value or None

    @error.setter
    def error(self, mensagem: str | None) -> None:
        self.aviso.value = mensagem or ""
        self.aviso.visible = bool(mensagem)

    def update(self) -> None:
        _atualizar(self.aviso)

    def _acoes(self, u) -> ft.Control:
        situacao = "Ativo" if u.ativo else "Inativo"
        botoes = [
            basicos.botao_secundario(
                "Redefinir senha", ft.Icons.LOCK_RESET, self._perguntar_redefinir
            ),
            basicos.botao_secundario(
                "Desconectar aparelhos", ft.Icons.DEVICES_OTHER_OUTLINED, self._perguntar_aparelhos
            ),
            basicos.botao_secundario(
                "Desativar" if u.ativo else "Reativar",
                ft.Icons.PERSON_OFF_OUTLINED if u.ativo else ft.Icons.PERSON_OUTLINE,
                self._perguntar_ativo,
            ),
        ]
        linhas = [basicos.rotulo_valor("Situação", situacao)]
        if u.deve_trocar_senha:
            linhas.append(basicos.subtitulo("A senha atual é temporária."))
        return basicos.cartao(basicos.coluna([basicos.titulo("Acesso"), *linhas, *botoes]))

    async def _notificacoes(self) -> ft.Control:
        """Prompt 32: o administrador vê o endereço e pode desligar as notificações;
        nunca grava nem confirma o endereço de outra pessoa."""
        self.cartao_email = ft.Container()
        await self._mostrar_notificacoes()
        return self.cartao_email

    async def _mostrar_notificacoes(self, n=None) -> None:
        if n is None:
            resultado = await self.app.chamar(
                notificacoes.obter_de_usuario, self.app.sessao.ator_id, self.usuario_id
            )
            if not resultado.ok:
                return
            n = resultado.valor
        if not n.disponivel and not n.email:
            self.cartao_email.content = None
            _atualizar(self.cartao_email)
            return
        linhas: list[ft.Control] = [
            basicos.titulo(TITULO_SECAO),
            basicos.rotulo_valor("E-mail", n.email or SEM_EMAIL),
            basicos.rotulo_valor(
                "Situação", texto_status_email(n.confirmado_em, n.email), uma_linha=True
            ),
            basicos.rotulo_valor(
                "Notificações", "Ativas" if n.notificacoes_ativas else "Desligadas"
            ),
        ]
        if n.notificacoes_ativas:

            async def desligar(_e=None) -> None:
                r = await self.app.chamar(
                    notificacoes.desativar_de_usuario, self.app.sessao.ator_id, self.usuario_id
                )
                if r.ok:
                    self.app.avisar("Notificações desligadas.")
                    await self._mostrar_notificacoes(r.valor)

            linhas.append(
                basicos.botao_secundario(
                    "Desligar notificações", ft.Icons.NOTIFICATIONS_OFF_OUTLINED, desligar
                )
            )
        self.cartao_email.content = basicos.cartao(basicos.coluna(linhas))
        _atualizar(self.cartao_email)

    async def _historico(self) -> ft.Control:
        resultado = await self.app.chamar(
            usuarios.listar_eventos_usuario, self.app.sessao.ator_id, self.usuario_id
        )
        linhas: list[ft.Control] = []
        for e in reversed(resultado.valor if resultado.ok else []):
            if e.valor_antigo is not None:
                texto = f"{e.campo}: {e.valor_antigo} -> {e.valor_novo}"
            else:
                texto = f"{e.campo}: {e.valor_novo}"
            linhas.append(
                ft.Column(
                    [
                        ft.Text(
                            f"{formatacao.formatar_data_hora(e.data_hora)}  ·  {e.autor}",
                            color=theme.COR_SUBTITULO,
                            size=theme.FONTE_PEQUENA,
                        ),
                        ft.Text(texto, color=theme.COR_TITULO, size=theme.FONTE_SUBTITULO),
                    ],
                    spacing=2,
                )
            )
        return basicos.cartao(basicos.coluna([basicos.titulo("Histórico"), *linhas]))

    # --- Gravação ---------------------------------------------------------------------

    async def _salvar(self, _e=None) -> None:
        if self.botao.disabled:
            return
        self.aviso.visible = False
        for campo in (self.nome, self.login):
            campo.error = None
        self.botao.disabled = True
        _atualizar(self.conteudo)
        try:
            if self.usuario is None:
                await self._criar()
            else:
                await self._alterar()
        finally:
            self.botao.disabled = False
            _atualizar(self.conteudo)

    async def _criar(self) -> None:
        resultado = await self.app.chamar(
            usuarios.criar_usuario,
            self.app.sessao.ator_id,
            self.nome.value or "",
            self.login.value or "",
            int(self.filial.value),
            self.papel.value,
            sorted(self.filiais.valor),
            campos=self.campos,
            erros_tratados=(ErroConflito,),
        )
        if isinstance(resultado.erro, ErroConflito):
            self.login.error = MSG_LOGIN_EXISTE
        elif resultado.ok:
            self._inicial = self._digitado()
            gerada = resultado.valor
            destino = rotas.rota_usuario(gerada.usuario.id)

            async def ir() -> None:
                await self.app.ir(destino, mensagem="Usuário criado.")

            self._mostrar_senha("Usuário criado", gerada, ir)

    async def _alterar(
        self, extra: dict | None = None, mensagem: str = "Usuário alterado."
    ) -> None:
        u = self.usuario
        alteracoes = extra or {
            campo: valor
            for campo, valor, antes in (
                ("nome", (self.nome.value or "").strip(), u.nome),
                ("filial_id", int(self.filial.value), u.filial_id),
                ("papel", self.papel.value, u.papel),
                ("filiais", sorted(self.filiais.valor), sorted(u.filiais)),
                ("especialidades", sorted(self.especialidades.valor), sorted(u.especialidades)),
            )
            if valor != antes
        }
        if not alteracoes:
            self.app.avisar("Nenhuma alteração para salvar.")
            return
        resultado = await self.app.chamar(
            usuarios.alterar_usuario,
            self.app.sessao.ator_id,
            u.id,
            u.versao,
            alteracoes,
            campos=self.campos,
            erros_tratados=(ErroConflito, ErroNaoEncontrado),
        )
        if resultado.ok:
            self._inicial = self._digitado()
            self.app.avisar(mensagem)
            self.conteudo.controls = [basicos.carregando()]
            await self.carregar()  # versão nova e histórico
        elif isinstance(resultado.erro, ErroConflito):
            self.error = MSG_CONFLITO
            self.app.avisar(MSG_CONFLITO)

    def _perguntar_aparelhos(self, _e=None) -> None:
        """Prompt 35: revoga todos os 'Lembrar de mim' do usuário."""

        async def revogar() -> None:
            r = await self.app.chamar(
                sessoes_lembradas.revogar_de_usuario, self.app.sessao.ator_id, self.usuario.id
            )
            if r.ok:
                self.app.avisar(f"{r.valor} aparelho(s) desconectado(s).")

        self.app.confirmar(
            "Desconectar aparelhos?",
            "Todos os aparelhos em que este usuário marcou 'Lembrar de mim' vão pedir a "
            "senha de novo.",
            "Desconectar",
            revogar,
        )

    def _perguntar_ativo(self, _e=None) -> None:
        ativo = self.usuario.ativo
        self.app.confirmar(
            "Desativar usuário?" if ativo else "Reativar usuário?",
            "O usuário não conseguirá mais entrar nem agir no sistema. O histórico das Ordens "
            "de Serviço continua."
            if ativo
            else "O usuário volta a poder entrar no sistema.",
            "Desativar" if ativo else "Reativar",
            lambda: self._alterar(
                {"ativo": not ativo}, "Usuário desativado." if ativo else "Usuário reativado."
            ),
        )

    def _perguntar_redefinir(self, _e=None) -> None:
        async def redefinir() -> None:
            resultado = await self.app.chamar(
                usuarios.redefinir_senha,
                self.app.sessao.ator_id,
                self.usuario.id,
                self.usuario.versao,
                erros_tratados=(ErroConflito,),
            )
            if isinstance(resultado.erro, ErroConflito):
                self.app.avisar(MSG_CONFLITO)
            elif resultado.ok:

                async def recarregar() -> None:
                    self.conteudo.controls = [basicos.carregando()]
                    await self.carregar()

                self._mostrar_senha("Senha redefinida", resultado.valor, recarregar)

        self.app.confirmar("Redefinir senha?", TEXTO_REDEFINIR, "Gerar senha", redefinir)

    def _mostrar_senha(self, titulo: str, gerada, depois) -> None:
        """A senha temporária, UMA vez. Fechar o diálogo a descarta da tela."""
        texto = ft.Text(
            gerada.senha_temporaria,
            selectable=True,
            color=theme.COR_TITULO,
            size=theme.FONTE_SAUDACAO,
            weight=ft.FontWeight.BOLD,
            font_family=theme.FONTE_FAMILIA,
        )

        async def fechar(_e=None) -> None:
            texto.value = ""
            self.app.page.pop_dialog()
            await depois()

        self.app.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                bgcolor=theme.COR_CARTAO,
                title=ft.Text(titulo, color=theme.COR_TITULO),
                content=ft.Container(
                    width=theme.LARGURA_MAX_LOGIN,
                    content=basicos.coluna(
                        [
                            basicos.subtitulo(
                                f"{ROTULO_SENHA_TEMPORARIA} de {gerada.usuario.login}:"
                            ),
                            texto,
                            basicos.subtitulo(AVISO_SENHA_UMA_VEZ),
                        ]
                    ),
                ),
                actions=[
                    ft.TextButton(
                        content="Já anotei",
                        style=theme.estilo_botao_texto(),
                        height=theme.ALVO_TOQUE_MIN,
                        on_click=fechar,
                    ),
                ],
            )
        )


class _ErroNaLista:
    def __init__(self, lista: ft.Dropdown) -> None:
        self.lista = lista

    @property
    def error(self) -> str | None:
        return self.lista.error_text

    @error.setter
    def error(self, mensagem: str | None) -> None:
        self.lista.error_text = mensagem

    def update(self) -> None:
        _atualizar(self.lista)
