"""Prompt 32: notificações por e-mail (endereço confirmado, consentimento, caixa de saída)."""

from __future__ import annotations

import email
import inspect
import os
import re
import threading
from datetime import UTC, datetime, timedelta
from email import policy

import pytest
from sqlalchemy import select

from osapp.db import sessao
from osapp.models import EmailFila, UsuarioNotificacao
from osapp.services import (
    email_mensagem,
    fila_email,
    lixeira,
    notificacoes,
    ordens,
    relogio,
)
from osapp.services.erros import ErroPermissao, ErroValidacao
from tests.conftest import config_alembic
from tests.fabricas import nova_filial, novo_usuario

T0 = datetime(2026, 11, 24, 13, 0, tzinfo=UTC)
CONFIG = fila_email.ConfigSmtp(
    "smtp.exemplo.invalid", 587, "remetente", "senha-ficticia", "os@exemplo.com.br", "starttls"
)


class Relogio:
    def __init__(self) -> None:
        self.agora = T0

    def __call__(self) -> datetime:
        return self.agora

    def andar(self, **delta) -> None:
        self.agora += timedelta(**delta)


@pytest.fixture
def clock(monkeypatch):
    r = Relogio()
    monkeypatch.setattr(relogio, "agora", r)
    return r


@pytest.fixture
def c(banco, clock, monkeypatch):
    """F001 e F002; um admin, manutenção nas duas filiais, um usuario (solicitante)."""
    monkeypatch.setenv("OS_BASE_URL", "https://os.exemplo.com.br")
    with sessao() as s:
        f1 = nova_filial(s, "F001", "Filial Modelo Norte")
        f2 = nova_filial(s, "F002", "Filial Modelo Sul")
        ids = {
            "f1": f1.id,
            "f2": f2.id,
            "admin": novo_usuario(s, f1, "admin", "Admin Fictício", papel="admin").id,
            "man1": novo_usuario(s, f1, "man.norte", "Manutenção Norte", papel="manutencao").id,
            "man2": novo_usuario(s, f2, "man.sul", "Manutenção Sul", papel="manutencao").id,
            "sol": novo_usuario(s, f1, "sol.norte", "Solicitante Norte", papel="usuario").id,
            "inativo": novo_usuario(
                s, f1, "man.inativo", "Inativo", papel="manutencao", ativo=True
            ).id,
        }
    return ids


def _ligar(usuario_id: int, email_: str, urgencia_minima: str = "baixa", ativas=True) -> None:
    """Grava direto (atalho de teste): endereço confirmado e notificações como pedido."""
    with sessao() as s:
        s.add(
            UsuarioNotificacao(
                usuario_id=usuario_id,
                email=email_,
                email_confirmado_em=T0 if ativas is not None else None,
                notificacoes_ativas=bool(ativas),
                urgencia_minima=urgencia_minima,
            )
        )


def _fila(tipo: str | None = None) -> list[EmailFila]:
    with sessao() as s:
        consulta = select(EmailFila).order_by(EmailFila.id)
        if tipo:
            consulta = consulta.where(EmailFila.tipo == tipo)
        return list(s.scalars(consulta))


def _destinos() -> set[str]:
    return {x.destinatario for x in _fila("nova_solicitacao")}


def _codigo_do_email() -> str:
    linha = _fila("codigo_confirmacao")[-1]
    return re.search(r"\b(\d{6})\b", linha.corpo).group(1)


# --- Destinatários ------------------------------------------------------------------------


def test_destinatarios_por_filial_papel_e_urgencia(c):
    _ligar(c["admin"], "admin@exemplo.com.br")
    _ligar(c["man1"], "norte@exemplo.com.br")
    _ligar(c["man2"], "sul@exemplo.com.br")
    ordens.criar_solicitacao(c["sol"], "Vazamento no tanque", "Descrição.", "baixa")
    # Admin: todas as filiais. Manutenção: só a própria (F001).
    assert _destinos() == {"admin@exemplo.com.br", "norte@exemplo.com.br"}
    ordens.criar_solicitacao(c["admin"], "Na filial sul", "Descrição.", "baixa", c["f2"])
    linhas = [x for x in _fila("nova_solicitacao") if "sul" in x.assunto.lower()]
    # O próprio solicitante (admin) não é avisado; manutenção do Sul é.
    assert {x.destinatario for x in linhas} == {"sul@exemplo.com.br"}


@pytest.mark.parametrize(
    ("minima", "urgencia", "recebe"),
    [
        ("baixa", "baixa", True),
        ("baixa", "media", True),
        ("alta", "media", False),
        ("alta", "alta", True),
        ("alta", "emergencial", True),
        ("emergencial", "alta", False),
        ("emergencial", "emergencial", True),
    ],
)
def test_urgencia_minima(c, minima, urgencia, recebe):
    _ligar(c["man1"], "norte@exemplo.com.br", minima)
    ordens.criar_solicitacao(c["sol"], "Título qualquer", "Descrição.", urgencia)
    assert (_destinos() == {"norte@exemplo.com.br"}) is recebe


def test_quem_nao_recebe(c):
    with sessao() as s:
        # usuario com registro (não deveria existir, mas o papel pode ter mudado depois)
        s.add(
            UsuarioNotificacao(
                usuario_id=c["sol"],
                email="sol@exemplo.com.br",
                email_confirmado_em=T0,
                notificacoes_ativas=True,
            )
        )
    _ligar(c["man1"], "naoconfirmado@exemplo.com.br", ativas=None)  # não confirmado
    _ligar(c["admin"], "desligado@exemplo.com.br", ativas=False)  # confirmado, desligado
    _ligar(c["inativo"], "inativo@exemplo.com.br")
    with sessao() as s:
        from osapp.models import Usuario

        s.get(Usuario, c["inativo"]).ativo = False
    # Filial F001: o usuario (papel), a manutenção não confirmada, o inativo e o admin
    # (desligado e, na primeira, o próprio solicitante) ficam de fora.
    ordens.criar_solicitacao(c["admin"], "Aberta pelo admin", "Descrição.", "emergencial", c["f1"])
    ordens.criar_solicitacao(c["sol"], "Na filial norte", "Descrição.", "emergencial")
    assert _destinos() == set()


def test_solicitante_nao_recebe_o_proprio_aviso(c):
    _ligar(c["man1"], "norte@exemplo.com.br")
    ordens.criar_solicitacao(c["man1"], "Aberta pela manutenção", "Descrição.", "alta")
    assert _destinos() == set()


def test_os_completa_nao_dispara(c):
    _ligar(c["admin"], "admin@exemplo.com.br")
    ordens.criar_os(c["man1"], "OS completa", "Descrição.", [])
    assert _fila() == []


def test_regra_pura_recebe():
    assert notificacoes.recebe("admin", 1, "baixa", 2, "baixa")
    assert not notificacoes.recebe("manutencao", 1, "baixa", 2, "baixa")
    assert not notificacoes.recebe("usuario", 1, "baixa", 1, "emergencial")
    assert not notificacoes.recebe("manutencao", 1, "emergencial", 1, "alta")


# --- Endereço e código ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("  Joana.Silva@Empresa.COM.br ", "Joana.Silva@empresa.com.br"),
        ("a@b.co", "a@b.co"),
        ("sem-arroba.com", None),
        ("dois@@a.com", None),
        ("a@b@c.com", None),
        ("a@semponto", None),
        ("a@.com", None),
        ("a@b..com", None),
        ("com espaco@a.com", None),
        ("a@b.com\r\nBcc: x@y.com", None),
        ("a\x00@b.com", None),
        ("<a>@b.com", None),
        ("x" * 65 + "@b.com", None),
        ("a@" + "b" * 250 + ".com", None),
        ("", None),
        (None, None),
    ],
)
def test_validacao_de_endereco(entrada, esperado):
    assert email_mensagem.normalizar_email(entrada) == esperado


def test_codigo_guardado_so_como_hash_e_confirmacao(c):
    estado = notificacoes.enviar_codigo(c["man1"], "norte@exemplo.com.br")
    assert estado.codigo_pendente and estado.confirmado_em is None
    codigo = _codigo_do_email()
    with sessao() as s:
        n = s.get(UsuarioNotificacao, c["man1"])
        assert n.codigo_hash and codigo not in n.codigo_hash and len(n.codigo_hash) == 64
        valores = [str(getattr(n, col.key)) for col in UsuarioNotificacao.__table__.columns]
        assert not any(codigo in v for v in valores)
    # Não confirmado: não pode ligar e não recebe.
    with pytest.raises(ErroValidacao) as erro:
        notificacoes.definir_notificacoes(c["man1"], True)
    assert erro.value.mensagem == notificacoes.MSG_NAO_CONFIRMADO
    ordens.criar_solicitacao(c["sol"], "Antes de confirmar", "Descrição.", "alta")
    assert _destinos() == set()
    estado = notificacoes.confirmar_codigo(c["man1"], codigo)
    assert estado.confirmado_em == T0 and not estado.codigo_pendente
    assert notificacoes.definir_notificacoes(c["man1"], True).notificacoes_ativas
    with sessao() as s:
        assert s.get(UsuarioNotificacao, c["man1"]).codigo_hash is None


def test_codigo_expira_em_15_minutos(c, clock):
    notificacoes.enviar_codigo(c["man1"], "norte@exemplo.com.br")
    codigo = _codigo_do_email()
    clock.andar(minutes=15)
    with pytest.raises(ErroValidacao) as erro:
        notificacoes.confirmar_codigo(c["man1"], codigo)
    assert erro.value.mensagem == notificacoes.MSG_CODIGO_EXPIRADO


def test_cinco_erros_bloqueiam_o_codigo(c):
    notificacoes.enviar_codigo(c["man1"], "norte@exemplo.com.br")
    codigo = _codigo_do_email()
    errado = f"{(int(codigo) + 1) % 1_000_000:06d}"
    for _ in range(5):
        with pytest.raises(ErroValidacao):
            notificacoes.confirmar_codigo(c["man1"], errado)
    with pytest.raises(ErroValidacao) as erro:
        notificacoes.confirmar_codigo(c["man1"], codigo)  # nem o certo vale mais
    assert erro.value.mensagem == notificacoes.MSG_CODIGO_BLOQUEADO
    with pytest.raises(ErroValidacao):
        notificacoes.confirmar_codigo(c["man1"], "12a456")  # formato


def test_limites_de_reenvio(c, clock):
    notificacoes.enviar_codigo(c["man1"], "norte@exemplo.com.br")
    with pytest.raises(ErroValidacao) as erro:
        notificacoes.enviar_codigo(c["man1"], "outro@exemplo.com.br")  # vale por usuário
    assert erro.value.mensagem == notificacoes.MSG_AGUARDE
    for _ in range(4):
        clock.andar(seconds=61)
        notificacoes.enviar_codigo(c["man1"], "norte@exemplo.com.br")
    clock.andar(seconds=61)
    with pytest.raises(ErroValidacao) as erro:
        notificacoes.enviar_codigo(c["man1"], "norte@exemplo.com.br")
    assert erro.value.mensagem == notificacoes.MSG_LIMITE_HORA
    assert len(_fila("codigo_confirmacao")) == 5
    # Só o último código pendente continua na fila; os anteriores foram cancelados.
    assert [x.status for x in _fila("codigo_confirmacao")].count("pendente") == 1
    clock.andar(hours=1)
    notificacoes.enviar_codigo(c["man1"], "norte@exemplo.com.br")


def test_trocar_endereco_apaga_a_confirmacao(c, clock):
    notificacoes.enviar_codigo(c["man1"], "norte@exemplo.com.br")
    notificacoes.confirmar_codigo(c["man1"], _codigo_do_email())
    notificacoes.definir_notificacoes(c["man1"], True)
    clock.andar(minutes=2)
    estado = notificacoes.enviar_codigo(c["man1"], "novo@exemplo.com.br")
    assert estado.email == "novo@exemplo.com.br"
    assert estado.confirmado_em is None and not estado.notificacoes_ativas
    ordens.criar_solicitacao(c["sol"], "Depois de trocar", "Descrição.", "alta")
    assert _destinos() == set()
    with pytest.raises(ErroValidacao):
        notificacoes.enviar_codigo(c["man1"], "pessoa @exemplo.com.br")


def test_remover_email(c):
    _ligar(c["man1"], "norte@exemplo.com.br")
    ordens.criar_solicitacao(c["sol"], "Pendente na fila", "Descrição.", "alta")
    estado = notificacoes.remover_email(c["man1"])
    assert estado.email is None and not estado.notificacoes_ativas
    assert [x.status for x in _fila()] == ["cancelado"]  # o pendente dele foi cancelado
    assert _fila()[0].corpo == ""


def test_urgencia_minima_invalida(c):
    assert notificacoes.definir_urgencia_minima(c["man1"], "alta").urgencia_minima == "alta"
    with pytest.raises(ErroValidacao):
        notificacoes.definir_urgencia_minima(c["man1"], "media")  # não é uma opção


# --- Permissões ----------------------------------------------------------------------------


def test_usuario_nao_tem_email(c):
    for chamada in (
        lambda: notificacoes.obter_minhas(c["sol"]),
        lambda: notificacoes.enviar_codigo(c["sol"], "sol@exemplo.com.br"),
        lambda: notificacoes.confirmar_codigo(c["sol"], "123456"),
        lambda: notificacoes.definir_notificacoes(c["sol"], True),
        lambda: notificacoes.definir_urgencia_minima(c["sol"], "baixa"),
        lambda: notificacoes.remover_email(c["sol"]),
    ):
        with pytest.raises(ErroPermissao):
            chamada()
    assert _fila() == []


def test_admin_desliga_mas_nao_grava_endereco_alheio(c):
    _ligar(c["man1"], "norte@exemplo.com.br")
    visto = notificacoes.obter_de_usuario(c["admin"], c["man1"])
    assert visto.email == "norte@exemplo.com.br" and visto.notificacoes_ativas
    depois = notificacoes.desativar_de_usuario(c["admin"], c["man1"])
    assert not depois.notificacoes_ativas and depois.email == "norte@exemplo.com.br"
    with pytest.raises(ErroPermissao):
        notificacoes.desativar_de_usuario(c["man2"], c["man1"])
    with pytest.raises(ErroPermissao):
        notificacoes.obter_de_usuario(c["man2"], c["man1"])
    # Não existe função que grave ou confirme o endereço de outro usuário: todas as de
    # gravação usam o próprio ator.
    for funcao in (
        notificacoes.enviar_codigo,
        notificacoes.confirmar_codigo,
        notificacoes.remover_email,
        notificacoes.definir_notificacoes,
        notificacoes.definir_urgencia_minima,
    ):
        parametros = list(inspect.signature(funcao).parameters)
        assert parametros[0] == "ator_id" and "usuario_id" not in parametros
    assert notificacoes.obter_de_usuario(c["admin"], c["sol"]).disponivel is False


def test_fila_de_emails_so_admin(c):
    with pytest.raises(ErroPermissao):
        fila_email.resumo_fila(c["man1"])
    with pytest.raises(ErroPermissao):
        fila_email.reenviar(c["man1"], 1)
    assert fila_email.resumo_fila(c["admin"]).contagens["pendente"] == 0


# --- Mensagem -----------------------------------------------------------------------------


def _mensagem(titulo: str):
    assunto = email_mensagem.assunto_nova_solicitacao("F001", "alta", titulo)
    msg = email_mensagem.montar_mensagem(
        7, "os@exemplo.com.br", "norte@exemplo.com.br", assunto, "corpo", T0
    )
    return email.message_from_bytes(msg.as_bytes(), policy=policy.default)


@pytest.mark.parametrize(
    "titulo",
    [
        "Vazamento\r\nBcc: x@y.com",
        "Vazamento\nBcc: x@y.com",
        "Vazamento\rBcc: x@y.com",
        "Vazamento\x00\x0b\x0c\x1b\u2028\u2029\x7fBcc: x@y.com",
        "Vazamento\u0085Bcc: x@y.com",
    ],
)
def test_titulo_nao_cria_cabecalho(titulo):
    lida = _mensagem(titulo)
    assert sorted(lida.keys()) == sorted(
        [
            "From",
            "To",
            "Subject",
            "Date",
            "Message-ID",
            "Content-Type",
            "Content-Transfer-Encoding",
            "MIME-Version",
        ]
    )
    assert lida["Bcc"] is None and lida["To"] == "norte@exemplo.com.br"
    assert lida["Subject"] == "[F001] [ALTA] Vazamento Bcc: x@y.com"
    assert lida["Message-ID"] == "<os-email-7@exemplo.com.br>"


def test_assunto_limitado_a_150():
    assunto = email_mensagem.assunto_nova_solicitacao("F001", "emergencial", "x" * 300)
    assert assunto.startswith("[F001] [EMERGENCIAL] ") and len(assunto) == 150
    assert email_mensagem.assunto_nova_solicitacao("F001", "media", "  a \t  b  ") == (
        "[F001] [MÉDIA] a b"
    )


def test_corpo_sem_custos_prioridade_nem_historico(c):
    _ligar(c["man1"], "norte@exemplo.com.br")
    v = ordens.criar_solicitacao(c["sol"], "Bomba parada", "Linha 1\nLinha 2", "emergencial")
    corpo = _fila()[0].corpo
    for proibido in (
        "custo",
        "previsto",
        "realizado",
        "prioridade",
        "executor",
        "histórico",
        "valor",
        "centavos",
        "sem_gasto",
        "R$",
    ):
        assert proibido not in corpo.lower(), proibido
    assert not re.search(r"\d+,\d{2}", corpo)  # nenhum valor em dinheiro formatado
    numero = ordens.listar_os(c["admin"]).itens[0].numero
    assert f"Número: {numero}" in corpo
    assert "Filial: F001 - Filial Modelo Norte" in corpo
    assert "Urgência: Emergencial" in corpo and "Solicitante: Solicitante Norte" in corpo
    assert "Aberta em: 24/11/2026 10:00" in corpo  # America/Sao_Paulo
    assert f"https://os.exemplo.com.br/os/{v.id}" in corpo
    assert corpo.rstrip().endswith(email_mensagem.RODAPE_NOTIFICACAO)
    assert _fila()[0].assunto == "[F001] [EMERGENCIAL] Bomba parada"


def test_email_do_codigo():
    corpo = email_mensagem.corpo_codigo("012345", 15)
    assert "012345" in corpo and "15 minutos" in corpo and "ignore" in corpo
    assert "http" not in corpo


def test_mascara():
    assert email_mensagem.mascarar("joana@empresa.com.br") == "j***@empresa.com.br"
    assert email_mensagem.mascarar(None) == "***"


# --- Entrega ---------------------------------------------------------------------------------


def _falha(_config, _msg):
    raise ConnectionRefusedError("sem rede")


def test_smtp_fora_do_ar_nao_afeta_a_os(c, clock, monkeypatch):
    _ligar(c["man1"], "norte@exemplo.com.br")
    monkeypatch.setenv("OS_EMAIL_MAX_TENTATIVAS", "3")
    v = ordens.criar_solicitacao(c["sol"], "Com SMTP fora", "Descrição.", "alta")
    assert ordens.obter_os(c["admin"], v.id).status == "ABERTA"
    r = fila_email.processar_lote(_falha, CONFIG)
    assert r.falhas == 1
    linha = _fila()[0]
    assert linha.status == "pendente" and linha.tentativas == 1
    assert linha.proxima_tentativa_em > clock.agora
    assert linha.ultimo_erro == "ConnectionRefusedError"
    # Ainda não venceu: nada é tentado.
    assert fila_email.processar_lote(_falha, CONFIG).falhas == 0
    for esperado in (2, 3):
        clock.andar(hours=2)
        fila_email.processar_lote(_falha, CONFIG)
        assert _fila()[0].tentativas == esperado
    assert _fila()[0].status == "falhou"


def test_espera_exponencial_com_teto():
    zero = lambda: 0.0  # noqa: E731
    assert [fila_email.espera(n, zero).total_seconds() / 60 for n in (1, 2, 3, 4, 7, 8, 20)] == [
        1,
        2,
        4,
        8,
        60,
        60,
        60,
    ]
    assert fila_email.espera(1, lambda: 1.0) == timedelta(minutes=1.1)


def test_envio_com_sucesso_e_message_id_estavel(c):
    _ligar(c["man1"], "norte@exemplo.com.br")
    ordens.criar_solicitacao(c["sol"], "Envio bom", "Descrição.", "alta")
    enviadas = []
    r = fila_email.processar_lote(lambda _c, m: enviadas.append(m), CONFIG)
    assert r.enviados == 1 and len(enviadas) == 1
    linha = _fila()[0]
    assert linha.status == "enviado" and linha.enviado_em is not None
    assert enviadas[0]["Message-ID"] == f"<os-email-{linha.id}@exemplo.com.br>"
    assert enviadas[0]["From"] == "os@exemplo.com.br"
    assert fila_email.processar_lote(lambda _c, m: enviadas.append(m), CONFIG).enviados == 0


def test_codigo_some_do_corpo_depois_de_enviado(c):
    notificacoes.enviar_codigo(c["man1"], "norte@exemplo.com.br")
    fila_email.processar_lote(lambda _c, _m: None, CONFIG)
    assert _fila("codigo_confirmacao")[0].corpo == ""


def test_sem_configuracao_fica_pendente(c, monkeypatch):
    for nome in ("OS_SMTP_HOST", "OS_SMTP_PORTA", "OS_SMTP_REMETENTE", "OS_SMTP_TLS"):
        monkeypatch.delenv(nome, raising=False)
    _ligar(c["man1"], "norte@exemplo.com.br")
    ordens.criar_solicitacao(c["sol"], "Sem config", "Descrição.", "alta")
    assert fila_email.processar_lote(_falha).sem_config
    assert _fila()[0].status == "pendente" and _fila()[0].tentativas == 0


def test_configuracao_smtp(monkeypatch):
    base = {
        "OS_SMTP_HOST": "smtp.exemplo.com.br",
        "OS_SMTP_PORTA": "587",
        "OS_SMTP_REMETENTE": "os@exemplo.com.br",
        "OS_SMTP_TLS": "starttls",
        "OS_SMTP_USUARIO": "os@exemplo.com.br",
        "OS_SMTP_SENHA": "segredo-ficticio",
    }
    for k, v in base.items():
        monkeypatch.setenv(k, v)
    config = fila_email.ler_config_smtp()
    assert config is not None and config.porta == 587
    assert "segredo-ficticio" not in repr(config)
    monkeypatch.setenv("OS_SMTP_TLS", "nenhum")
    assert fila_email.ler_config_smtp() is None  # sem TLS só em localhost
    monkeypatch.setenv("OS_SMTP_HOST", "localhost")
    assert fila_email.ler_config_smtp() is not None
    monkeypatch.setenv("OS_SMTP_PORTA", "abc")
    assert fila_email.ler_config_smtp() is None


def test_os_excluida_cancela_o_aviso(c):
    _ligar(c["man1"], "norte@exemplo.com.br")
    v = ordens.criar_solicitacao(c["sol"], "Vai para a lixeira", "Descrição.", "alta")
    d = ordens.obter_os(c["admin"], v.id)
    lixeira.excluir_os(c["admin"], v.id, d.versao, "Aberta por engano, duplicada.")
    enviadas = []
    r = fila_email.processar_lote(lambda _c, m: enviadas.append(m), CONFIG)
    assert r.cancelados == 1 and enviadas == []
    assert _fila()[0].status == "cancelado"


def test_concessao_vencida_volta_a_pendente(c, clock):
    _ligar(c["man1"], "norte@exemplo.com.br")
    ordens.criar_solicitacao(c["sol"], "Processo morreu", "Descrição.", "alta")
    reservadas, _ = fila_email.reservar(clock.agora)
    assert len(reservadas) == 1 and _fila()[0].status == "enviando"
    assert fila_email.reservar(clock.agora)[0] == []  # já reservada
    clock.andar(minutes=6)
    assert len(fila_email.reservar(clock.agora)[0]) == 1


def test_reenviar_falhou_e_retencao(c, clock):
    _ligar(c["man1"], "norte@exemplo.com.br")
    ordens.criar_solicitacao(c["sol"], "Vai falhar", "Descrição.", "alta")
    with sessao() as s:
        linha = s.scalars(select(EmailFila)).one()
        linha.status, linha.tentativas, linha.ultimo_erro = "falhou", 6, "SMTPConnectError"
        linha_id = linha.id
    resumo = fila_email.resumo_fila(c["admin"])
    assert resumo.contagens["falhou"] == 1
    assert resumo.erros[0].destino == "n***@exemplo.com.br" and resumo.erros[0].pode_reenviar
    assert not hasattr(resumo.erros[0], "corpo")
    fila_email.reenviar(c["admin"], linha_id)
    assert _fila()[0].status == "pendente" and _fila()[0].tentativas == 0
    with pytest.raises(ErroValidacao):
        fila_email.reenviar(c["admin"], linha_id)  # só 'falhou'
    # Retenção
    fila_email.processar_lote(lambda _c, _m: None, CONFIG)
    assert fila_email.limpar_fila(clock.agora + timedelta(days=29)) == (0, 0)
    assert fila_email.limpar_fila(clock.agora + timedelta(days=31)) == (1, 0)
    assert _fila() == []


def test_trabalhador_nao_derruba_o_app(c, monkeypatch, caplog):
    import asyncio

    monkeypatch.delenv("OS_SMTP_HOST", raising=False)
    t = fila_email.Trabalhador(intervalo=0.01)

    async def rodar():
        t.iniciar()
        await asyncio.sleep(0.1)
        await t.parar()

    with caplog.at_level("WARNING", logger="osapp.services.fila_email"):
        asyncio.run(rodar())
    avisos = [r for r in caplog.records if "não configurado" in r.getMessage()]
    assert len(avisos) == 1  # uma vez por hora, não a cada rodada


def test_logs_sem_endereco_nem_corpo(c, caplog):
    _ligar(c["man1"], "norte@exemplo.com.br")
    with caplog.at_level("INFO"):
        ordens.criar_solicitacao(c["sol"], "Título secreto", "Descrição secreta.", "alta")
        notificacoes.enviar_codigo(c["admin"], "admin@exemplo.com.br")
        fila_email.processar_lote(_falha, CONFIG)
        fila_email.processar_lote(lambda _c, _m: None, CONFIG)
    texto = "\n".join(r.getMessage() for r in caplog.records)
    for proibido in ("norte@exemplo.com.br", "admin@exemplo.com.br", "secret", CONFIG.senha):
        assert proibido not in texto
    assert "n***@exemplo.com.br" in texto


# --- Concorrência (PostgreSQL) ------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("OS_TEST_DATABASE_URL"),
    reason="SKIP LOCKED só existe no PostgreSQL (OS_TEST_DATABASE_URL)",
)
def test_dois_trabalhadores_nunca_pegam_a_mesma_linha(c, clock):
    _ligar(c["man1"], "norte@exemplo.com.br")
    for i in range(30):
        ordens.criar_solicitacao(c["sol"], f"Solicitação {i:02d}", "Descrição.", "alta")
    pegas: list[list[int]] = [[], []]
    barreira = threading.Barrier(2)

    def trabalhar(n: int) -> None:
        barreira.wait()
        for _ in range(10):
            reservadas, _ = fila_email.reservar(clock.agora, limite=4)
            pegas[n].extend(r.id for r in reservadas)

    threads = [threading.Thread(target=trabalhar, args=(n,)) for n in (0, 1)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not set(pegas[0]) & set(pegas[1])
    assert sorted(pegas[0] + pegas[1]) == sorted(x.id for x in _fila())


# --- Migração ---------------------------------------------------------------------------------


def test_migracao_0013_com_dados(banco_vazio):
    from alembic import command
    from sqlalchemy import MetaData
    from sqlalchemy import inspect as inspecionar

    from osapp import db

    cfg = config_alembic()
    command.upgrade(cfg, "0012")
    db.reiniciar()
    engine = db.obter_engine()
    m = MetaData()
    m.reflect(bind=engine)
    with engine.begin() as conn:
        conn.execute(m.tables["filiais"].insert().values(id=1, codigo="F001", nome="Norte"))
        conn.execute(
            m.tables["usuarios"]
            .insert()
            .values(id=1, nome="A", login="a", senha_hash="x", filial_id=1, papel="admin", versao=1)
        )
    command.upgrade(cfg, "0013")
    db.reiniciar()
    nomes = set(inspecionar(db.obter_engine()).get_table_names())
    assert {"usuario_notificacao", "email_fila"} <= nomes
    _ligar(1, "a@exemplo.com.br")
    with sessao() as s:
        assert s.get(UsuarioNotificacao, 1).notificacoes_ativas
        s.add(
            EmailFila(
                tipo="codigo_confirmacao",
                destinatario="a@exemplo.com.br",
                assunto="x",
                corpo="y",
                status="pendente",
                proxima_tentativa_em=T0,
                criado_em=T0,
                usuario_id=1,
            )
        )
    # O banco recusa notificação ligada sem endereço confirmado.
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), sessao() as s:
        s.get(UsuarioNotificacao, 1).email_confirmado_em = None
        s.flush()
    command.downgrade(cfg, "0012")
    db.reiniciar()
    nomes = set(inspecionar(db.obter_engine()).get_table_names())
    assert "usuario_notificacao" not in nomes and "email_fila" not in nomes
    assert "usuarios" in nomes
    with db.obter_engine().connect() as conn:
        assert conn.execute(select(m.tables["usuarios"].c.login)).scalars().all() == ["a"]
    command.upgrade(cfg, "head")


# --- Interface (funções puras e montagem dos controles) ---------------------------------


def test_textos_da_secao_e_quem_ve():
    from osapp.ui.views import notificacoes_email as tela
    from osapp.ui.views.perfil import tem_secao_email

    assert tem_secao_email("manutencao") and tem_secao_email("admin")
    assert not tem_secao_email("usuario")
    assert tela.texto_status(None, None) == "Nenhum e-mail cadastrado"
    assert tela.texto_status(None, "a@b.com") == "Não confirmado"
    assert tela.texto_status(T0, "a@b.com") == "Confirmado em 24/11/2026"
    assert [v for v, _ in tela.OPCOES_URGENCIA_MINIMA] == list(notificacoes.URGENCIAS_MINIMAS)
    assert [r for _, r in tela.OPCOES_URGENCIA_MINIMA] == [
        "Todas",
        "Alta e acima",
        "Somente emergencial",
    ]


def test_secao_monta_com_cada_estado():
    from types import SimpleNamespace

    from osapp.ui.views.notificacoes_email import FilaEmails, SecaoEmail

    secao = SecaoEmail(SimpleNamespace(sessao=SimpleNamespace(ator_id=1)))
    assert secao.receber.disabled and not secao.botao_remover.visible
    secao._mostrar(notificacoes.MinhasNotificacoes("a@b.com", None, False, "alta", True))
    assert secao.bloco_codigo.visible and secao.receber.disabled
    assert secao.urgencia.valor == "alta"
    secao._mostrar(notificacoes.MinhasNotificacoes("a@b.com", T0, True, "baixa", False))
    assert not secao.receber.disabled and secao.receber.value
    assert not secao.bloco_codigo.visible and secao.botao_remover.visible
    assert FilaEmails(SimpleNamespace()).conteudo is not None
