"""Preparação do piloto (prompt 41): o ÚNICO apagamento físico permitido no sistema, e só
para este reinício antes do piloto (docs/REGRAS.md).

Apaga as ordens de teste e tudo o que depende delas (itens, eventos, fila de e-mails,
'lembrar de mim', contadores de tentativas de login) e reinicia a numeração. Mantém
filiais, categorias, tipos, especialidades, alvos de SLA, motivos de cancelamento e os
usuários existentes (o administrador incluído). Cria usuários de teste com nomes
fictícios realistas, com senha temporária gerada (mostrada uma vez) e troca obrigatória;
rodar de novo não duplica os usuários.

As confirmações (flag, nome do banco digitado, ambiente de produção) ficam no comando de
linha (osapp/cli.py); esta função só faz o trabalho, numa transação.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import delete, func, select

from osapp.db import sessao
from osapp.models import (
    EmailFila,
    Filial,
    OrdemServico,
    OsEvento,
    OsItemCusto,
    OsSequencia,
    SessaoLembrada,
    TentativaLogin,
)
from osapp.repositories import UsuarioRepo
from osapp.services import usuarios

logger = logging.getLogger(__name__)

# Nomes fictícios, logins nome.sobrenome (nunca 'manutencao1' ou 'usuario.teste').
USUARIOS_DO_PILOTO: tuple[tuple[str, str, str], ...] = (
    ("Ana Ribeiro", "ana.ribeiro", "usuario"),
    ("Bruno Cardoso", "bruno.cardoso", "usuario"),
    ("Carla Mendes", "carla.mendes", "manutencao"),
    ("Diego Moraes", "diego.moraes", "manutencao"),
    ("Elisa Fonseca", "elisa.fonseca", "admin"),
)


@dataclass(frozen=True)
class UsuarioCriado:
    nome: str
    login: str
    papel: str
    senha_temporaria: str  # mostrada uma vez pelo comando; nunca em log

    def __repr__(self) -> str:
        return f"UsuarioCriado(login={self.login!r}, papel={self.papel!r}, senha='***')"


@dataclass(frozen=True)
class ResultadoPiloto:
    ordens_apagadas: int
    eventos_apagados: int
    itens_apagados: int
    emails_apagados: int
    sessoes_apagadas: int
    tentativas_apagadas: int
    criados: tuple[UsuarioCriado, ...]
    ja_existiam: tuple[str, ...]


def plano() -> list[str]:
    """O que o comando vai fazer (impresso antes da confirmação)."""
    return [
        "APAGAR (definitivo): todas as Ordens de Serviço, seus itens de custo e eventos,",
        "  a fila de e-mails, os 'lembrar de mim' e os contadores de tentativas de login;",
        "  reiniciar a numeração das OS (cada filial volta ao número 1).",
        "MANTER: filiais, categorias, tipos, especialidades, alvos de SLA, motivos de",
        "  cancelamento e todos os usuários existentes (o administrador incluído).",
        "CRIAR (se ainda não existirem): "
        + ", ".join(f"{nome} ({login}, {papel})" for nome, login, papel in USUARIOS_DO_PILOTO)
        + ", com senha temporária e troca no primeiro acesso.",
    ]


def preparar() -> ResultadoPiloto:
    with sessao() as s:

        def apagar(modelo) -> int:
            # Core sobre a tabela: sem eventos do ORM nem o filtro da lixeira.
            return s.execute(delete(modelo.__table__)).rowcount or 0

        emails = apagar(EmailFila)
        itens = apagar(OsItemCusto)
        eventos = apagar(OsEvento)
        ordens = apagar(OrdemServico)
        apagar(OsSequencia)
        sessoes = apagar(SessaoLembrada)
        tentativas = apagar(TentativaLogin)

        filial = s.scalars(select(Filial).order_by(Filial.id)).first()
        if filial is None:
            raise RuntimeError("Nenhuma filial cadastrada: crie uma antes.")
        repo = UsuarioRepo(s)
        criados: list[UsuarioCriado] = []
        existentes: list[str] = []
        for nome, login, papel in USUARIOS_DO_PILOTO:
            if repo.obter_por_login(login) is not None:
                existentes.append(login)
                continue
            senha = usuarios.gerar_senha_temporaria()
            usuarios.criar(s, None, nome, login, filial.id, papel, senha, temporaria=True)
            criados.append(UsuarioCriado(nome, login, papel, senha))
        restantes = s.scalar(select(func.count()).select_from(OrdemServico.__table__))
        assert restantes == 0
    logger.info(
        "Piloto preparado: %s ordens, %s eventos, %s itens apagados; %s usuários criados.",
        ordens,
        eventos,
        itens,
        len(criados),
    )
    return ResultadoPiloto(
        ordens, eventos, itens, emails, sessoes, tentativas, tuple(criados), tuple(existentes)
    )
