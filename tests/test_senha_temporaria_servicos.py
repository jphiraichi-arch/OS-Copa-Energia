"""Lacuna do prompt 22 (docs/ESTADO.md): a troca obrigatória de senha valia só pela guarda
de rotas da interface. Agora os serviços também recusam quem ainda tem senha temporária,
exceto trocar a própria senha, 'lembrar de mim' no login e sair deste aparelho."""

from __future__ import annotations

import pytest

from osapp.db import sessao
from osapp.models import Usuario
from osapp.services import ordens, sessoes_lembradas, usuarios
from osapp.services.auth import carregar_ator
from osapp.services.erros import ErroAutenticacao, ErroTrocaDeSenhaPendente
from tests.fabricas import nova_filial, novo_usuario

SENHA_TEMP = "Temporaria-123"


@pytest.fixture
def temp(banco):
    from osapp.services import senhas

    with sessao() as s:
        f = nova_filial(s, "1007", "Jardinópolis")
        u = novo_usuario(s, f, "ana.ribeiro", "Ana Ribeiro", papel="manutencao")
        u.senha_hash = senhas.gerar_hash(SENHA_TEMP)
        u.deve_trocar_senha = True
        return u.id


def test_servicos_recusam_quem_tem_senha_temporaria(temp):
    with pytest.raises(ErroTrocaDeSenhaPendente):
        carregar_ator(temp)
    with pytest.raises(ErroTrocaDeSenhaPendente):
        ordens.listar_os(temp)
    with pytest.raises(ErroTrocaDeSenhaPendente):
        ordens.criar_solicitacao(temp, "Lâmpada queimada", "Corredor.", "baixa")
    assert issubclass(ErroTrocaDeSenhaPendente, ErroAutenticacao)  # a interface sai


def test_trocar_lembrar_e_sair_continuam_permitidos(temp):
    emitido = sessoes_lembradas.lembrar(temp, "Mozilla/5.0 (Windows NT 10.0) Firefox/120.0")
    sessoes_lembradas.sair_deste_aparelho(temp, emitido.familia)
    usuarios.trocar_propria_senha(temp, SENHA_TEMP, "Senha-Nova-Bem-Longa-1")
    with sessao() as s:
        assert s.get(Usuario, temp).deve_trocar_senha is False
    assert ordens.listar_os(temp).itens == ()  # depois da troca, tudo liberado
