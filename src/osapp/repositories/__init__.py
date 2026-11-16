"""Repositórios: acesso a dados pelo ORM, sem regra de negócio nem verificação de permissão."""

from osapp.repositories.filial_repo import FilialRepo
from osapp.repositories.ordem_servico_repo import OrdemServicoRepo
from osapp.repositories.os_evento_repo import OsEventoRepo
from osapp.repositories.usuario_repo import UsuarioRepo

__all__ = ["FilialRepo", "OrdemServicoRepo", "OsEventoRepo", "UsuarioRepo"]
