"""Rótulos da tela principal e da navegação, em um só lugar. Módulo puro (sem Flet).

Regra: nestes rótulos escreve-se "Ordem de Serviço" por extenso, nunca a sigla.
O número da ordem (por exemplo OS-2026-000001) é dado gravado, não rótulo.
"""

from __future__ import annotations

TITULO_DO_APP = "Sistema de Ordens de Serviço"

# --- Navegação principal ---------------------------------------------------------------
# Barra inferior (celular): cabe por extenso com dois destinos a 390 px.
NAVEGACAO_ORDENS = "Ordens de Serviço"
NAVEGACAO_NOVA_ORDEM = "Nova Ordem de Serviço"
# Trilho lateral (telas largas): coluna estreita, o mesmo texto em duas linhas.
TRILHO_ORDENS = "Ordens de\nServiço"
TRILHO_NOVA_ORDEM = "Nova Ordem\nde Serviço"

# --- Menu do cabeçalho -----------------------------------------------------------------
MENU_CONFIGURACOES = "Configurações"
MENU_SAIR = "Sair"

# --- Home ------------------------------------------------------------------------------
HOME_TITULO = "Ordens de Serviço"
HOME_BUSCA = "Buscar"
HOME_BUSCA_DICA = "Número, título ou descrição"
HOME_BUSCAR = "Buscar"
HOME_TODAS = "Todas"
HOME_FILIAL = "Filial"
HOME_TODAS_AS_FILIAIS = "Todas as filiais"
HOME_ATUALIZAR = "Atualizar"
HOME_CARREGAR_MAIS = "Carregar mais"
HOME_VAZIA = "Nenhuma Ordem de Serviço encontrada."

# --- Configurações ---------------------------------------------------------------------
CONFIG_TITULO = "Configurações"
CONFIG_CARTAO_USUARIO = "Usuário"
CONFIG_CARTAO_APLICATIVO = "Aplicativo"
CONFIG_NOME = "Nome"
CONFIG_LOGIN = "Usuário (login)"
CONFIG_FILIAL = "Filial"
CONFIG_PERFIL = "Perfil"
CONFIG_VERSAO = "Versão"
PERFIL_ADMINISTRADOR = "Administrador"
PERFIL_USUARIO = "Usuário"
