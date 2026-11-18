"""Modelos ORM. Importar este pacote registra as quatro tabelas em ``Base.metadata``."""

from osapp.models.custos import CategoriaCusto, OsItemCusto
from osapp.models.equipamento import Equipamento
from osapp.models.filial import Filial
from osapp.models.ordem_servico import OrdemServico
from osapp.models.os_evento import OsEvento
from osapp.models.os_sequencia import OsSequencia
from osapp.models.usuario import Usuario

__all__ = [
    "CategoriaCusto",
    "Equipamento",
    "Filial",
    "OrdemServico",
    "OsEvento",
    "OsItemCusto",
    "OsSequencia",
    "Usuario",
]
