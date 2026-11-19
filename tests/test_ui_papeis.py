"""Prompt 19: navegação por papel, rótulos e ordenação de 'Solicitações abertas'."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from osapp.services import ordens, status
from osapp.services.auth import PAPEIS
from osapp.ui import navegacao, rotas, rotulos

T0 = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)


def rotas_de(papel):
    return [d.rota for d in navegacao.destinos(papel)]


def test_navegacao_por_papel():
    assert rotas_de("usuario") == [rotas.HOME, rotas.SOLICITACAO_NOVA]
    # Relatórios (prompt 18): primeiro nível para manutenção e administrador.
    assert rotas_de("manutencao") == [rotas.HOME, rotas.OS_NOVA, rotas.RELATORIOS]
    assert rotas_de("admin") == [
        rotas.HOME,
        rotas.OS_NOVA,
        rotas.SOLICITACAO_NOVA,
        rotas.RELATORIOS,
    ]
    assert rotas_de("desconhecido") == [rotas.HOME]
    assert [d.rotulo for d in navegacao.destinos("usuario")] == ["Ordens", "Nova Solicitação"]
    # Relatórios: nunca para o usuario.
    assert not navegacao.ve_relatorios("usuario")
    assert navegacao.ve_relatorios("manutencao") and navegacao.ve_relatorios("admin")
    assert all(rotas.resolver(d.rota) for p in PAPEIS for d in navegacao.destinos(p))


def test_todo_valor_tem_rotulo():
    assert {s: rotulos.status(s) for s in status.ROTULOS} == {
        "ABERTA": "Aberta",
        "EM_EXECUCAO": "Em execução",
        "CONCLUIDA": "Concluída",
        "CANCELADA": "Cancelada",
    }
    assert [rotulos.nivel(n) for n in ordens.NIVEIS] == ["Baixa", "Média", "Alta", "Emergencial"]
    assert rotulos.nivel(None) == "Não definida"
    assert [rotulos.origem(o) for o in ordens.ORIGENS] == ["Solicitação", "Manutenção"]
    assert [rotulos.papel(p) for p in PAPEIS] == ["Usuário", "Manutenção", "Administrador"]


def test_cores_de_nivel_e_status_vem_do_tema():
    from osapp.ui import theme

    assert theme.cores_status("CANCELADA") == theme.COR_STATUS_CANCELADA
    cores = {n: theme.cores_nivel(n) for n in ordens.NIVEIS}
    assert len(set(cores.values())) == 4  # cada urgência tem a sua
    assert cores["emergencial"] == theme.COR_NIVEL_EMERGENCIAL  # a que mais se destaca


@dataclass
class Item:
    id: int
    urgencia: str | None
    aberta_em: datetime


@pytest.mark.parametrize("embaralhar", [False, True])
def test_ordenacao_das_solicitacoes_abertas(embaralhar):
    h = timedelta(hours=1)
    itens = [
        Item(1, "baixa", T0 - 9 * h),
        Item(2, "emergencial", T0 - h),
        Item(3, "alta", T0 - 2 * h),
        Item(4, "emergencial", T0 - 5 * h),
        Item(5, None, T0 - 99 * h),
        Item(6, "media", T0 - 3 * h),
        Item(7, "alta", T0 - 7 * h),
    ]
    if embaralhar:
        itens = list(reversed(itens))
    ordem = [i.id for i in rotulos.ordenar_solicitacoes_abertas(itens)]
    # Emergencial primeiro; dentro da mesma urgência, a mais antiga antes; sem urgência no fim.
    assert ordem == [4, 2, 7, 3, 6, 1, 5]


def test_rotas_novas():
    assert rotas.resolver("/solicitacao/nova") == ("solicitacao_nova", {})
    assert rotas.resolver("/os/7/assumir") == ("os_assumir", {"os_id": 7})
    assert rotas.resolver("/os/7/solicitacao") == ("os_solicitacao", {"os_id": 7})
    assert rotas.rota_anterior("/os/7/assumir") == "/os/7"
    assert rotas.rota_anterior("/solicitacao/nova") == "/"
    assert rotas.resolver("/relatorios/mensal") == ("relatorios_mensal", {})
    assert rotas.rota_anterior("/relatorios/mensal") == "/relatorios"
