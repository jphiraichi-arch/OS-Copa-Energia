# Próximos passos

Funcionalidades adiadas e onde cada uma se encaixa no desenho atual.

**Status cancelada.** Nova constante e rótulo em `services/status.py`, entradas em
`TRANSICOES` (por exemplo `ABERTA -> CANCELADA`) e inclusão em `ENCERRADOS`. Uma função
`cancelar_os` em `services/ordens.py` reutiliza `_mudar_status`; a Home já monta os chips a
partir de `ROTULOS`, falta só a cor em `theme.cores_status`.

**Reabrir uma OS concluída.** Uma entrada `CONCLUIDA -> EM_EXECUCAO` (ou `-> ABERTA`) em
`TRANSICOES`, com uma regra nova de "quem pode" (só administrador). A função de serviço
decide o que fazer com os campos de realizado (manter no histórico e limpar na OS).

**Triagem.** Um status anterior a `ABERTA` (por exemplo `EM_TRIAGEM`) como `STATUS_INICIAL`
e uma transição feita por um papel de triagem. Papéis além de `is_admin` pedem uma coluna
nova em `usuarios` e uma função em `services/permissoes.py`.

**Aceite pela operação.** Um status entre `EM_EXECUCAO` e `CONCLUIDA` (por exemplo
`AGUARDANDO_ACEITE`) com transições de aceitar e recusar em `TRANSICOES`. Os eventos já
registram quem fez cada mudança; o Detalhe ganha os botões a partir de novas flags em `AcoesOs`.

**KPIs.** Um serviço novo (`services/indicadores.py`) com consultas agregadas por filial e
período sobre `ordens_servico`, usando `pode_acessar_filial`. Uma rota nova em `ui/rotas.py`
e um destino na navegação; as diferenças previsto x realizado já são calculadas em `_detalhe`.

**Fotos.** Tabela `os_anexos` (os_id, usuario_id, caminho, criado_em) com repositório e
funções de serviço que respeitam `_carregar_visivel`. O envio usa o diretório de upload do
Flet (`upload_dir` em `ft.run`) e um cartão novo no Detalhe.

**Notificações.** Um ponto único depois de `registrar_evento` em `services/ordens.py`
publica o evento (fila ou tabela `notificacoes`). O envio (e-mail, push) fica em um serviço
separado, fora da transação da OS.

**Planos preventivos.** Tabelas `planos_preventivos` e sua agenda; um comando em `cli.py`
(executado por agendador) chama `criar_os` com um usuário de sistema. As OS geradas seguem
o fluxo normal e ganham uma coluna opcional `plano_id`.

**Estoque.** Tabelas `itens` e `os_itens` (quantidade e custo em centavos) com serviço
próprio; a conclusão pode somar os itens ao valor realizado. As regras de filial são as
mesmas, via `pode_acessar_filial`.

**Exportação PDF/Excel.** Um serviço que recebe os mesmos filtros de `listar_os` (sem
paginação) e devolve os dados; a geração do arquivo fica em um módulo à parte, com
dependência nova. A formatação reutiliza `osapp/formatacao.py`.

**Telas de administração de usuários e filiais.** `services/administracao.py` já tem
`criar_filial`, `criar_usuario`, `redefinir_senha` e `desativar_usuario`; faltam versões com
`ator_id` que comecem por `carregar_ator` e `exigir_admin`. Rotas novas em `ui/rotas.py`,
visíveis no menu só para administrador.

**Troca de senha pelo usuário.** Uma função `trocar_senha(ator_id, senha_atual, senha_nova)`
em `services/auth.py`, que confere a senha atual com `senhas.verificar` e valida a nova com
`validar_senha`. Uma tela simples acessada pelo menu do cabeçalho.

**Antes do PostgreSQL.** Trocar `valor_previsto_centavos` e `valor_realizado_centavos` para
`BigInteger` (ver `docs/AUDITORIA.md`, item d), adicionar o driver (por exemplo `psycopg`)
e rodar a suíte com `OS_TEST_DATABASE_URL`.
