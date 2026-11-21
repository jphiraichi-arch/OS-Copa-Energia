"""Criação de dados fictícios para os testes."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from osapp.db import sessao
from osapp.models import CategoriaCusto, Filial, OrdemServico, TipoManutencao, Usuario
from osapp.repositories import FilialRepo, OrdemServicoRepo, UsuarioRepo
from osapp.services.custos import ItemEntrada


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
        "tempo_previsto_minutos": 60,
        "criado_em": datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    }
    dados.update(extras)
    return OrdemServicoRepo(s).adicionar(
        OrdemServico(numero=numero, filial_id=filial.id, criado_por_id=criador.id, **dados)
    )


def categoria_id(codigo: str = "OUTROS") -> int:
    with sessao() as s:
        return s.scalars(select(CategoriaCusto.id).where(CategoriaCusto.codigo == codigo)).one()


def itens(valor_centavos: object, descricao: str = "Valor total", codigo: str = "OUTROS"):
    """Uma lista com um item de quantidade 1 (o equivalente ao antigo preço único)."""
    return [ItemEntrada(categoria_id(codigo), descricao, Decimal("1"), valor_centavos)]


def tipo_id(codigo: str = "CORRETIVA") -> int:
    with sessao() as s:
        return s.scalars(select(TipoManutencao.id).where(TipoManutencao.codigo == codigo)).one()


def args_de_criacao(dados: dict) -> dict:
    """Converte os argumentos antigos de criar_os (valor_previsto_centavos) nos novos e
    completa o previsto (tipo, prioridade) para a OS poder ser iniciada."""
    dados = dict(dados)
    if "valor_previsto_centavos" in dados:
        dados["itens_previstos"] = itens(dados.pop("valor_previsto_centavos"))
    dados.setdefault("tipo_id", tipo_id())
    dados.setdefault("prioridade", "media")
    return dados


NOTA = "Serviço feito conforme o previsto."


def args_de_conclusao(dados: dict) -> dict:
    dados = dict(dados)
    if "valor_realizado_centavos" in dados:
        dados["itens_realizados"] = itens(dados.pop("valor_realizado_centavos"))
    dados.setdefault("nota_conclusao", NOTA)
    return dados
