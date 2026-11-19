from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm.exc import StaleDataError

from osapp.db import sessao
from osapp.models import Filial, OrdemServico, OsEvento, Usuario
from tests.fabricas import nova_filial, nova_os, novo_usuario


def test_filial_codigo_unico(banco):
    with sessao() as s:
        nova_filial(s, "F001")
    with pytest.raises(IntegrityError), sessao() as s:
        nova_filial(s, "F001", "Outra")


def test_usuario_login_unico_e_em_minusculas(banco):
    with sessao() as s:
        f = nova_filial(s)
        u = novo_usuario(s, f, login="Marina.Teste")
        assert u.login == "marina.teste"
    with pytest.raises(IntegrityError), sessao() as s:
        novo_usuario(s, s.get(Filial, 1), login="MARINA.TESTE")


def test_os_numero_unico(banco):
    with sessao() as s:
        f = nova_filial(s)
        u = novo_usuario(s, f)
        nova_os(s, f, u, "OS-2026-000001")
    with pytest.raises(IntegrityError), sessao() as s:
        nova_os(s, s.get(Filial, 1), s.get(Usuario, 1), "OS-2026-000001")


def test_chave_estrangeira_invalida_e_rejeitada(banco):
    with pytest.raises(IntegrityError), sessao() as s:
        s.add(Usuario(nome="Sem Filial", login="sem.filial", senha_hash="x", filial_id=9999))
    with sessao() as s:
        f = nova_filial(s)
        u = novo_usuario(s, f)
        uid = u.id
    with pytest.raises(IntegrityError), sessao() as s:
        s.add(OsEvento(os_id=9999, usuario_id=uid, tipo="CRIACAO"))


def test_padroes_do_usuario(banco):
    with sessao() as s:
        u = novo_usuario(s, nova_filial(s))
        uid = u.id
    with sessao() as s:
        u = s.get(Usuario, uid)
        assert (u.is_admin, u.ativo) == (False, True)


@pytest.mark.parametrize("extras", [{"tempo_previsto_minutos": 0}, {"tempo_previsto_minutos": -1}])
def test_check_constraints(banco, extras):
    with pytest.raises(IntegrityError), sessao() as s:
        f = nova_filial(s)
        nova_os(s, f, novo_usuario(s, f), **extras)


def test_timestamp_volta_com_fuso_utc_e_igual(banco):
    instante = datetime(2026, 3, 1, 15, 30, 45, 123000, tzinfo=UTC)
    em_sao_paulo = datetime(2026, 3, 1, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
    with sessao() as s:
        f = nova_filial(s)
        u = novo_usuario(s, f)
        o = nova_os(s, f, u, criado_em=instante, inicio_realizado=em_sao_paulo)
        oid = o.id
    with sessao() as s:
        lido = s.get(OrdemServico, oid).criado_em
        assert lido == instante
        assert lido.tzinfo is not None and lido.utcoffset() == timedelta(0)
        iniciado = s.get(OrdemServico, oid).inicio_realizado
        assert iniciado == em_sao_paulo
        assert iniciado.utcoffset() == timedelta(0) and iniciado.hour == 12
        assert s.get(OrdemServico, oid).fim_realizado is None


def test_timestamp_sem_fuso_e_recusado(banco):
    with pytest.raises(StatementError), sessao() as s:
        f = nova_filial(s)
        nova_os(s, f, novo_usuario(s, f), criado_em=datetime(2026, 3, 1, 15, 30))


def test_versao_comeca_em_1_e_protege_contra_escrita_concorrente(banco):
    with sessao() as s:
        f = nova_filial(s)
        o = nova_os(s, f, novo_usuario(s, f))
        oid = o.id
        assert o.versao == 1
    with sessao() as a:
        oa = a.get(OrdemServico, oid)
        with sessao() as b:
            b.get(OrdemServico, oid).titulo = "Alterado por B"
        oa.titulo = "Alterado por A"
        with pytest.raises(StaleDataError):
            a.flush()
        a.rollback()
    with sessao() as s:
        o = s.get(OrdemServico, oid)
        assert (o.titulo, o.versao) == ("Alterado por B", 2)


def test_sessao_desfaz_em_caso_de_erro(banco):
    with pytest.raises(RuntimeError), sessao() as s:
        nova_filial(s)
        raise RuntimeError("falha simulada")
    with sessao() as s:
        assert s.query(Filial).count() == 0
