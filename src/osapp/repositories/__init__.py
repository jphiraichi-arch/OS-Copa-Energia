"""Repositórios: acesso a dados pelo ORM, sem regra de negócio nem verificação de permissão."""

from osapp.repositories.cadastros_repo import CategoriaCustoRepo, EquipamentoRepo
from osapp.repositories.filial_repo import FilialRepo
from osapp.repositories.ordem_servico_repo import OrdemServicoRepo
from osapp.repositories.os_evento_repo import OsEventoRepo
from osapp.repositories.os_sequencia_repo import OsSequenciaRepo
from osapp.repositories.usuario_repo import UsuarioRepo

__all__ = [
    "CategoriaCustoRepo",
    "EquipamentoRepo",
    "FilialRepo",
    "OrdemServicoRepo",
    "OsEventoRepo",
    "OsSequenciaRepo",
    "UsuarioRepo",
]
