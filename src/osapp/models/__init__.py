"""Modelos ORM. Importar este pacote registra as quatro tabelas em ``Base.metadata``."""

from osapp.models.filial import Filial
from osapp.models.ordem_servico import OrdemServico
from osapp.models.os_evento import OsEvento
from osapp.models.usuario import Usuario

__all__ = ["Filial", "OrdemServico", "OsEvento", "Usuario"]
