"""Numeração das OS: '{filial}-{ano}-{sequência}', por filial e ano, segura sob concorrência."""

from __future__ import annotations

import threading
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from osapp.db import sessao
from osapp.models import OrdemServico, OsSequencia
from osapp.repositories import OrdemServicoRepo
from osapp.services import ordens, relogio
from osapp.services.erros import ErroConflito
from tests.fabricas import itens, nova_filial, novo_usuario

MEIO_DE_2026 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def jardinopolis(banco, monkeypatch):
    monkeypatch.setenv("OS_TZ", "America/Sao_Paulo")
    monkeypatch.setattr(relogio, "agora", lambda: MEIO_DE_2026)
    with sessao() as s:
        filial = nova_filial(s, "1007", "Jardinópolis")
        outra = nova_filial(s, "1008", "Filial de teste")
        return {
            "filial": filial.id,
            "u1": novo_usuario(s, filial, "u1.teste", "Usuária Um").id,
            "u2": novo_usuario(s, outra, "u2.teste", "Usuário Dois").id,
        }


def criar(ator_id):
    return ordens.criar_os(
        ator_id,
        "Troca de rolamento",
        "Descrição.",
        itens(100),
        60,
    )


def contador(filial_id, ano):
    with sessao() as s:
        linha = s.get(OsSequencia, (filial_id, ano))
        return None if linha is None else linha.ultimo_numero


def test_formato_e_sequencia(jardinopolis):
    assert criar(jardinopolis["u1"]).numero == "1007-2026-000001"
    assert criar(jardinopolis["u1"]).numero == "1007-2026-000002"
    assert contador(jardinopolis["filial"], 2026) == 2
    assert ordens.formatar_numero("1007", 2027, 123456) == "1007-2027-123456"


def test_uma_sequencia_por_filial(jardinopolis):
    criar(jardinopolis["u1"])
    assert criar(jardinopolis["u2"]).numero == "1008-2026-000001"
    assert criar(jardinopolis["u1"]).numero == "1007-2026-000002"


def test_ano_novo_recomeca_em_1(jardinopolis, monkeypatch):
    criar(jardinopolis["u1"])
    criar(jardinopolis["u1"])
    monkeypatch.setattr(relogio, "agora", lambda: datetime(2027, 1, 10, 12, 0, tzinfo=UTC))
    assert criar(jardinopolis["u1"]).numero == "1007-2027-000001"


def test_ano_vem_do_fuso_local_nao_do_utc(jardinopolis, monkeypatch):
    # 31/12/2026 23:30 em São Paulo = 01/01/2027 02:30 em UTC
    monkeypatch.setattr(relogio, "agora", lambda: datetime(2027, 1, 1, 2, 30, tzinfo=UTC))
    assert criar(jardinopolis["u1"]).numero == "1007-2026-000001"
    # 01/01/2027 00:30 em São Paulo
    monkeypatch.setattr(relogio, "agora", lambda: datetime(2027, 1, 1, 3, 30, tzinfo=UTC))
    assert criar(jardinopolis["u1"]).numero == "1007-2027-000001"


def test_falha_depois_de_sortear_o_numero_nao_consome_o_numero(jardinopolis, monkeypatch):
    criar(jardinopolis["u1"])
    original = ordens.registrar_evento

    def falhar(*_a, **_k):
        raise RuntimeError("falha simulada depois de sortear o número")

    monkeypatch.setattr(ordens, "registrar_evento", falhar)
    with pytest.raises(RuntimeError):
        criar(jardinopolis["u1"])
    assert contador(jardinopolis["filial"], 2026) == 1  # o incremento foi desfeito
    monkeypatch.setattr(ordens, "registrar_evento", original)
    assert criar(jardinopolis["u1"]).numero == "1007-2026-000002"


def test_numero_repetido_vira_erro_conflito_e_nao_grava_nada(jardinopolis):
    primeira = criar(jardinopolis["u1"])
    with sessao() as s:  # contador "voltou" (por exemplo, restaurado à mão)
        s.get(OsSequencia, (jardinopolis["filial"], 2026)).ultimo_numero = 0
    with pytest.raises(ErroConflito):
        criar(jardinopolis["u1"])
    with sessao() as s:
        assert s.scalar(select(func.count()).select_from(OrdemServico)) == 1
        assert s.get(OsSequencia, (jardinopolis["filial"], 2026)).ultimo_numero == 0
    assert primeira.numero == "1007-2026-000001"


def test_numeros_antigos_continuam_valendo(jardinopolis):
    """OS criadas antes (formato 'OS-AAAA-NNNNNN') não mudam e não colidem com as novas."""
    with sessao() as s:
        from osapp.models import Usuario

        u = s.get(Usuario, jardinopolis["u1"])
        OrdemServicoRepo(s).adicionar(
            OrdemServico(
                numero="OS-2026-000001",
                filial_id=u.filial_id,
                criado_por_id=u.id,
                titulo="Antiga",
                descricao="Antiga.",
                status="ABERTA",
                tempo_previsto_minutos=1,
                criado_em=MEIO_DE_2026,
                atualizado_em=MEIO_DE_2026,
            )
        )
    assert criar(jardinopolis["u1"]).numero == "1007-2026-000001"
    with sessao() as s:
        assert sorted(s.scalars(select(OrdemServico.numero))) == [
            "1007-2026-000001",
            "OS-2026-000001",
        ]


def test_vinte_criacoes_simultaneas(jardinopolis):
    """No PostgreSQL: 20 threads ao mesmo tempo recebem 20 números distintos e consecutivos.

    No SQLite o teste é pulado: o SQLite serializa toda escrita no arquivo inteiro e,
    com várias conexões escrevendo juntas, responde 'database is locked' em vez de
    esperar. Lá ele não provaria a trava de linha (FOR UPDATE não existe no SQLite).
    """
    with sessao() as s:
        if s.get_bind().dialect.name != "postgresql":
            pytest.skip("concorrência real só no PostgreSQL (OS_TEST_DATABASE_URL)")
    total = 20
    largada = threading.Barrier(total)
    numeros, erros = [], []

    def trabalho():
        try:
            largada.wait(timeout=30)
            numeros.append(criar(jardinopolis["u1"]).numero)
        except Exception as erro:  # noqa: BLE001
            erros.append(repr(erro))

    threads = [threading.Thread(target=trabalho) for _ in range(total)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert erros == []
    assert sorted(numeros) == [f"1007-2026-{n:06d}" for n in range(1, total + 1)]
    assert contador(jardinopolis["filial"], 2026) == total
