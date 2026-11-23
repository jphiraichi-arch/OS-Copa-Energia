"""Rótulos da tela principal e da navegação, em um só lugar. Módulo puro (sem Flet).

Regra: nestes rótulos escreve-se "Ordem de Serviço" por extenso, nunca a sigla.
O número da ordem (por exemplo OS-2026-000001) é dado gravado, não rótulo.
"""

from __future__ import annotations

TITULO_DO_APP = "Sistema de Ordens de Serviço"
MARCA_ROTULO = "Copa Energia"

# --- Navegação principal ---------------------------------------------------------------
# Barra inferior em todos os tamanhos de tela (decisão de 21/11/2026). 'Nova OS' é a única
# forma abreviada permitida, e só na barra inferior (o teste de rótulos tem a exceção).
NAVEGACAO_NOVA_OS = "Nova OS"
NAVEGACAO_ORDENS = "Ordens"
NAVEGACAO_RELATORIOS = "Relatórios"
NAVEGACAO_PERFIL = "Perfil"

# --- Login -----------------------------------------------------------------------------
LOGIN_MARCA = "Ordens de Serviço"

# --- Perfil -------------------------------------------------------------------------------
PERFIL_TITULO = "Perfil"
MENU_CONFIGURACOES = "Configurações"
MENU_ALTERAR_SENHA = "Alterar senha"
MENU_USUARIOS = "Usuários"
MENU_NOVA_SOLICITACAO = "Nova Solicitação"
MENU_SAIR = "Sair"

# --- Faixa (banner) ------------------------------------------------------------------------
BANNER_ABERTAS = "Abertas"
BANNER_AGUARDANDO = "Aguardando início"

# --- Home ------------------------------------------------------------------------------
HOME_TITULO = "Ordens de Serviço"
HOME_BUSCA = "Buscar"
HOME_BUSCA_DICA = "Número ou palavras do título, da descrição ou dos itens"
TEMPOS_BUSCA_DICA = "Palavras dos itens (ou de tudo)"
HOME_BUSCA_DICA_USUARIO = "Número, ou palavras do título e da descrição"
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
CONFIG_PAPEL = "Papel"
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
    "Valores em dinheiro e desempenho por pessoa são visíveis apenas para manutenção "
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


# --- Relatório de tempos de atendimento (prompt 18) ------------------------------------
TEMPOS_TITULO = "Relatório de tempos de atendimento"
TEMPOS_PERIODO = "Período (data em que a solicitação foi aberta)"
TEMPOS_DE = "De (dd/mm/aaaa)"
TEMPOS_ATE = "Até (dd/mm/aaaa)"
TEMPOS_APLICAR = "Aplicar"
TEMPOS_RESPOSTA = "Tempo de resposta"
TEMPOS_RESPOSTA_AJUDA = "Da abertura até o início da execução."
TEMPOS_SOLUCAO = "Tempo até solução"
TEMPOS_SOLUCAO_AJUDA = "Da abertura até a conclusão."
TEMPOS_MEDIA = "Média"
TEMPOS_MEDIANA = "Mediana"
TEMPOS_POR_URGENCIA = "Por urgência"
TEMPOS_ABERTAS = "Solicitações em aberto"
TEMPOS_QUANTIDADE = "Quantidade"
TEMPOS_MAIS_ANTIGA = "mais antiga há"
TEMPOS_NOTA = (
    "Média sente casos extremos; mediana mostra o caso típico. Horas corridas, sem "
    "calendário de expediente."
)
TEMPOS_VAZIO = "Sem dados no período."
TEMPOS_BUSCA = "Buscar no relatório"
TEMPOS_FILTRADO_POR = "filtrado por:"
TEMPOS_BUSCA_VAZIA = "Nenhuma ordem corresponde à busca no período."
TEMPOS_CUSTOS = "Custos das ordens encontradas"
TEMPOS_PREVISTO_TODAS = "Previsto (todas as encontradas)"
TEMPOS_CUSTOS_NOTA = (
    "Previsto x realizado: só as {n} ordem(ns) concluída(s); as demais ainda não têm realizado."
)
TEMPOS_PREVISTO = "Previsto"
TEMPOS_REALIZADO = "Realizado"
TEMPOS_DIFERENCA = "Diferença"
TEMPOS_ORDENS = "Ordens encontradas"
TEMPOS_PAGINA_ANTERIOR = "Página anterior"
TEMPOS_PROXIMA_PAGINA = "Próxima página"
TEMPOS_MENSAL = "Relatório mensal (custos e desempenho)"
HOME_ATALHO_RELATORIO = "Relatório de tempos de atendimento"
HOME_ATALHO_RELATORIO_AJUDA = "Tempo de resposta e até a solução das solicitações."
