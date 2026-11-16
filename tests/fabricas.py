"""Criação de dados fictícios para os testes."""

from __future__ import annotations

from datetime import UTC, datetime

from osapp.models import Filial, OrdemServico, Usuario
from osapp.repositories import FilialRepo, OrdemServicoRepo, UsuarioRepo


def nova_filial(s, codigo="F001", nome="Filial Modelo Norte") -> Filial:
    return FilialRepo(s).adicionar(Filial(codigo=codigo, nome=nome))


def novo_usuario(s, filial, login="marina.teste", nome="Marina Teste", **extras) -> Usuario:
    return UsuarioRepo(s).adicionar(
        Usuario(nome=nome, login=login, senha_hash="nao-e-um-hash", filial_id=filial.id, **extras)
    )


def nova_os(s, filial, criador, numero="OS-2026-000001", **extras) -> OrdemServico:
    dados = {
        "titulo": "Troca de rolamento",
        "descricao": "Esteira com ruído.",
        "status": "ABERTA",
        "valor_previsto_centavos": 10000,
        "tempo_previsto_minutos": 60,
        "criado_em": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    }
    dados.update(extras)
    return OrdemServicoRepo(s).adicionar(
        OrdemServico(numero=numero, filial_id=filial.id, criado_por_id=criador.id, **dados)
    )
