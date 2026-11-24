"""Modelos ORM. Importar este pacote registra as tabelas em ``Base.metadata``."""

from osapp.models.custos import CategoriaCusto, OsItemCusto
from osapp.models.filial import Filial
from osapp.models.notificacao import EmailFila, UsuarioNotificacao
from osapp.models.ordem_servico import OrdemServico
from osapp.models.os_evento import OsEvento
from osapp.models.os_sequencia import OsSequencia
from osapp.models.tentativa_login import TentativaLogin
from osapp.models.tipo_manutencao import TipoManutencao
from osapp.models.usuario import Usuario
from osapp.models.usuario_evento import UsuarioEvento

__all__ = [
    "CategoriaCusto",
    "EmailFila",
    "Filial",
    "OrdemServico",
    "OsEvento",
    "OsItemCusto",
    "OsSequencia",
    "TentativaLogin",
    "TipoManutencao",
    "Usuario",
    "UsuarioEvento",
    "UsuarioNotificacao",
]
