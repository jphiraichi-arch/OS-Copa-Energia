"""Repositórios: acesso a dados pelo ORM, sem regra de negócio nem verificação de permissão."""

from osapp.repositories.cadastros_repo import (
    CategoriaCustoRepo,
    EspecialidadeRepo,
    MotivoCancelamentoRepo,
    TipoManutencaoRepo,
)
from osapp.repositories.filial_repo import FilialRepo
from osapp.repositories.notificacao_repo import AlertaRepo, EmailFilaRepo, NotificacaoRepo
from osapp.repositories.ordem_servico_repo import OrdemServicoRepo
from osapp.repositories.os_evento_repo import OsEventoRepo
from osapp.repositories.os_sequencia_repo import OsSequenciaRepo
from osapp.repositories.tentativa_login_repo import TentativaLoginRepo
from osapp.repositories.usuario_repo import UsuarioRepo

__all__ = [
    "AlertaRepo",
    "CategoriaCustoRepo",
    "EmailFilaRepo",
    "EspecialidadeRepo",
    "FilialRepo",
    "MotivoCancelamentoRepo",
    "NotificacaoRepo",
    "OrdemServicoRepo",
    "OsEventoRepo",
    "OsSequenciaRepo",
    "TentativaLoginRepo",
    "TipoManutencaoRepo",
    "UsuarioRepo",
]
