"""Rótulos da tela principal e da navegação, em um só lugar. Módulo puro (sem Flet).

Regra: nestes rótulos escreve-se "Ordem de Serviço" por extenso, nunca a sigla.
O número da ordem (por exemplo OS-2026-000001) é dado gravado, não rótulo.
"""

from __future__ import annotations

TITULO_DO_APP = "Sistema de Ordens de Serviço"

# --- Navegação principal ---------------------------------------------------------------
# Barra inferior (celular): três destinos em 390 px, por isso a forma curta por extenso.
NAVEGACAO_ORDENS = "Ordens"
NAVEGACAO_NOVA_ORDEM = "Nova Ordem"
NAVEGACAO_RELATORIOS = "Relatórios"
# Trilho lateral (telas largas): o nome completo, em duas linhas.
TRILHO_ORDENS = "Ordens de\nServiço"
TRILHO_NOVA_ORDEM = "Nova Ordem\nde Serviço"
TRILHO_RELATORIOS = "Relatórios"

# --- Login -----------------------------------------------------------------------------
LOGIN_MARCA = "Ordens de Serviço"

# --- Menu do cabeçalho -----------------------------------------------------------------
MENU_CONFIGURACOES = "Configurações"
MENU_RELATORIOS = "Relatórios"
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
PERFIL_GERENTE = "Gerente"
PERFIL_USUARIO = "Usuário"

# --- Relatórios ------------------------------------------------------------------------
REL_TITULO = "Relatórios"
REL_MES_ANTERIOR = "Mês anterior"
REL_PROXIMO_MES = "Próximo mês"
REL_FILIAL = "Filial"
REL_TODAS_AS_FILIAIS = "Todas as filiais"
REL_SITUACAO = "Situação atual das Ordens de Serviço"
REL_MOVIMENTO = "Movimento do mês"
REL_CRIADAS = "Criadas no mês"
REL_CONCLUIDAS = "Concluídas no mês"
REL_TEMPO_MEDIO = "Tempo médio de execução"
REL_CUSTOS = "Custos do mês"
REL_CUSTOS_NOTA = "Ordens de Serviço concluídas no mês."
REL_PREVISTO = "Valor previsto"
REL_GASTO = "Gasto total (realizado)"
REL_DIFERENCA_VALOR = "Diferença de valor"
REL_TEMPO_PREVISTO = "Tempo previsto"
REL_TEMPO_REALIZADO = "Tempo realizado"
REL_DIFERENCA_TEMPO = "Diferença de tempo"
REL_ACIMA = "Acima do valor previsto"
REL_DESVIOS = "Maiores estouros de custo"
REL_EXECUTORES = "Desempenho por executor"
REL_FILIAIS = "Por filial"
REL_RESTRITO = (
    "Valores em dinheiro e desempenho por pessoa são visíveis apenas para gerentes "
    "e administradores."
)
REL_NENHUMA_CONCLUIDA = "Nenhuma Ordem de Serviço concluída neste mês."
REL_ERRO = "Não foi possível carregar o relatório."
MESES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def nome_do_mes(ano: int, mes: int) -> str:
    """Ex.: 'novembro de 2026'."""
    return f"{MESES[mes - 1]} de {ano}"
