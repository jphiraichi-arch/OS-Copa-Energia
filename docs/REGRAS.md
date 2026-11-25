# Regras permanentes do projeto — Sistema de OS

Este arquivo é vinculante para todos os prompts. `docs/ESTADO.md` registra o que já existe.

## STACK (fixa)

- Python 3.12+ em Linux, venv + pip. O projeto instala com: `pip install -e '.[dev]'`
- Flet 1.1.x, fixado como `flet>=1.1,<1.2`, rodando como app web no lado do servidor: o Python
  roda no servidor, o navegador mostra a interface. Não é build estático nem Pyodide.
- SQLAlchemy 2 + Alembic (adicionados no prompt 2). SQLite em desenvolvimento, PostgreSQL depois.
- pytest e ruff como dependências de desenvolvimento.

## REGRA DO FLET (crítica)

O Flet 1.0 foi uma reescrita completa; código Flet escrito de memória ou copiado de tutoriais
antigos normalmente falha. Antes de usar qualquer API do Flet:

1. Confirme a versão instalada com: `pip show flet`
2. Consulte a API na documentação atual em https://flet.dev/docs, ou pelo servidor MCP oficial
   (pacote PyPI `flet-mcp`, iniciado com o comando `flet mcp`). Não use o pacote comunitário
   não relacionado chamado `flet-mcp-server`.
3. Exemplos de armadilhas conhecidas (lista incompleta): `ft.app(target=main)` virou
   `ft.run(main)`; `page.go()` virou o assíncrono `page.push_route()`; `ElevatedButton` virou
   `Button`.
4. O Flet 1.1 mudou as superfícies padrão do tema para branco neutro / quase preto; portanto
   defina explicitamente toda cor de que o app precisa.
5. Use os controles Material padrão, não os controles com estilo shadcn adicionados na 1.1.

Se não for possível verificar uma API, pare e avise. Não adivinhe.

## Camadas

- `models -> repositories -> services -> ui`.
- Regras de negócio e verificações de permissão vivem somente em `services`.
- Views nunca importam `models` nem `repositories`.

## Segurança

- Senhas com hash argon2id; nunca armazenadas nem registradas em log em texto puro.
- Toda verificação de permissão e de filial é aplicada em `services` e coberta por teste.
- Acesso ao banco somente pelo ORM do SQLAlchemy, com parâmetros vinculados.
- Toda entrada é validada no lado do servidor.
- Segredos e a URL do banco ficam somente em variáveis de ambiente.
- O usuário vê mensagens de erro genéricas; os detalhes vão para os logs do servidor.
- Dados de seed usam apenas nomes fictícios.

## Papéis e permissões (prompt 17; substituem as regras de perfil dos prompts 3 a 5)

Toda função de serviço começa por `carregar_ator`; usuário inativo é recusado em tudo.

- **usuario** (outras áreas): abre solicitações (título, descrição, urgência) e acompanha
  as OS da própria filial pelo modelo reduzido (`OsVisaoSolicitante`, `ResumoSolicitante`).
  Nunca recebe previsto, realizado, custos, tipo, prioridade, executor nem o
  histórico: a consulta nem lê essas colunas. Edita e cancela só a própria solicitação,
  enquanto ABERTA.
- **manutencao**: assume e executa as OS da própria filial; cria OS completas; edita os
  campos da manutenção até a conclusão; nunca muda a urgência do solicitante.
- **admin**: tudo, em todas as filiais. Só ele muda a filial de uma OS e edita OS concluída.
- **Relatório mensal** (decisão de 21/11/2026): manutenção vê o da própria filial, com
  custos; administrador vê qualquer filial ou o consolidado, com custos; o papel usuario
  não tem acesso (ErroPermissao). O sinalizador `is_gerente` não muda mais o acesso.
- Status e transições ficam em `services/status.py` (dados). CONCLUIDA e CANCELADA são
  finais: só o administrador edita uma concluída; ninguém edita uma cancelada.
- Os instantes `aberta_em`, `inicio_execucao_em`, `concluida_em` e `cancelada_em` só são
  gravados pelas transições, com `relogio.agora()`, na mesma transação do evento STATUS;
  nunca vêm da entrada.
- As flags de `acoes` são calculadas pelas mesmas funções que permitem ou recusam.
- Dados sensíveis (valores em dinheiro, desempenho por pessoa) só saem do serviço para
  manutenção (própria filial) e administrador. A interface apenas mostra o que recebe.
- Campos de dinheiro, duração e hora: nunca reescrever o valor do campo em `on_change`
  (em 4G lento isso perde dígitos). Formatar ao sair do campo (`on_blur`) e validar ao
  gravar, com as funções puras de `ui/leitura.py`.

## Idioma

- Interface em português do Brasil; datas `dd/mm/aaaa`; moeda `R$ 1.234,56`.
- Identificadores de domínio em português (`filial`, `usuario`, `ordem_servico`).

## Armazenamento

- Dinheiro em centavos inteiros, durações em minutos inteiros, instantes (timestamps) em UTC.

## Interface

- `src/osapp/ui/theme.py` é a única fonte de cores, raios e tamanhos. Nenhum valor hexadecimal
  de cor pode aparecer em outro arquivo de `src/osapp` (garantido por `tests/test_tema.py`).
- Texto desenhado só com a fonte embutida (`theme.FONTE_FAMILIA`, arquivos em
  `src/osapp/assets/fonts`), e o app sobe com `no_cdn=True`: nada de fonte ou motor gráfico
  baixado de CDN. Todo caractere usado em rótulos precisa existir na fonte (há teste).
- Celulares são o alvo principal: coluna única, sem rolagem horizontal a 390 px; alvo de toque
  mínimo de 48 px.
- O único logotipo permitido é o arquivo oficial da Copa Energia fornecido pelo responsável,
  `src/osapp/assets/logo.png`: sem redesenhar, recolorir nem distorcer. Nenhum outro
  logotipo real de empresa.

## Itens de custo (prompt 13, regras finais conferidas no prompt 29)

- Papéis só pelo campo `papel` (usuario, manutencao, admin); não existe coluna booleana
  de administrador (a propriedade derivada chama-se `e_admin`).
- Cada fase (previsto e realizado) tem exatamente uma de duas coisas: pelo menos um item,
  OU a marca 'Sem gasto' (`sem_gasto_previsto`, `sem_gasto_realizado`) — nunca as duas
  (prompt 31; substitui 'pelo menos um item'). Iniciar exige o previsto assim; concluir,
  o realizado. Faltando as duas: 'Adicione um item ou marque Sem gasto.'
- PREVISTO: manutenção da filial da ordem ou administrador incluem, alteram, removem e
  marcam 'Sem gasto' enquanto a ordem não está concluída; depois da conclusão, só o
  administrador. Opcional enquanto ABERTA; a partir de Em execução a fase sempre tem item
  ou 'Sem gasto' (remover o último item só por `trocar_para_sem_gasto`).
- REALIZADO: chega com a conclusão (itens ou 'Sem gasto'), pelo executor ou
  administrador; depois, só o administrador altera; antes da conclusão ninguém grava.
  Ordem cancelada: ninguém.
- Marcar 'Sem gasto' exige a fase sem itens; incluir um item desmarca. Toda mudança da
  marca vai para o histórico, na mesma transação. As marcas são informação de custo: o
  papel usuario nunca as recebe.
- `criar_os` (manutenção e administrador) aceita lista vazia de itens previstos e tempo
  vazio; `criar_solicitacao` não tem itens. `concluir_os` exige itens realizados ou
  `sem_gasto_realizado`, os instantes realizados e a nota.
- `previsto_completo()` é a única verificação para iniciar: tempo previsto, pelo menos 1
  item previsto ou 'Sem gasto', tipo e prioridade (numa solicitação, a prioridade vazia é preenchida
  com a urgência ao iniciar — prompt 24). Não existe equipamento em lugar nenhum.
- O papel usuario nunca recebe itens, totais ou nada derivado deles: nem na lista, no
  detalhe, na busca (não busca nos itens), nas sugestões ou nos relatórios.

## Exclusão lógica e Lixeira (prompt 24)

- Ordem de Serviço nunca é apagada do banco: nenhum código emite DELETE em
  `ordens_servico` (há teste estático e um `before_delete` que levanta erro). Excluir é
  `services/lixeira.excluir_os` (só administrador, motivo de 10 a 500 caracteres, sem dados
  pessoais); restaurar é `restaurar_os`. Eventos EXCLUSAO e RESTAURACAO no histórico.
- **Toda consulta nova respeita a exclusão lógica.** O filtro é central: um evento
  `do_orm_execute` (models/ordem_servico.py) acrescenta `excluida_em IS NULL` a toda
  consulta ORM que toque OrdemServico (select, Session.get, contagens, subconsultas,
  junções, carga de relacionamentos). Não escreva consultas Core (`conexao.execute` em
  tabelas) que leiam ordens fora de migrações. Só a lixeira usa a opção de execução
  `INCLUIR_EXCLUIDAS` (e as rotinas administrativas `recalcular-busca` e a consolidação de
  filiais, que precisam tratar todas as ordens).
- Ordem excluída some para todos os papéis (administrador também) de listas, busca,
  detalhe, contadores, selo, sugestões e relatórios; aberta pelo endereço, dá o mesmo
  ErroNaoEncontrado de uma ordem inexistente. Ninguém a edita, muda o status ou os itens
  até ser restaurada. O número nunca é reutilizado.
- Prioridade: ao iniciar uma solicitação sem prioridade, o serviço copia a urgência (mesma
  escala) e grava um EDICAO com a observação "Sugerida pela urgência do solicitante". A
  urgência nunca muda.

## Layout (prompt 23; leia antes de mexer em qualquer tela)

- Toda tela usa os componentes de `src/osapp/ui/components/`: `banner` (faixa no topo das
  telas principais, com a filial e os contadores), `SecaoCard`/`secao` (seções numeradas),
  `status_pill`, `opcao_card`/`OpcaoGrupo` (escolhas importantes), `GrupoChips` (escolhas
  pequenas), `basicos` (campos, botões, cartões). Tela nova não monta cabeçalho, navegação,
  cartão nem formulário próprios.
- Formulários são seções numeradas (`SecaoCard`): '1. SOLICITAÇÃO', '2. URGÊNCIA'... As
  seções de cada papel e status vêm de `ui/secoes.py` (função pura, testada). Seção que o
  papel não usa não é desenhada e o dado dela não é pedido ao serviço. Esconder uma seção
  nunca é controle de segurança: o serviço decide.
- Escolha única importante (urgência): `OpcaoGrupo` de cartões com ponto colorido, rótulo,
  significado e a etiqueta 'SELECIONADO'. Escolhas pequenas (tipo, prioridade, filtros de
  status, escopo da busca): chips.
- Navegação: barra inferior em todos os tamanhos de tela ('Nova OS' · 'Ordens' com selo ·
  'Relatórios' para manutenção e administrador · 'Perfil'), definida por
  `ui/navegacao.destinos(papel)`. 'Nova OS' é a única abreviação permitida, só na barra.
  Barra superior fina com voltar, logotipo e filial; sem menu de três barras nem trilho.
- Conteúdo centralizado com no máximo `theme.LARGURA_MAX_CONTEUDO` (1100 px); abaixo de
  `theme.LARGURA_CELULAR_MAX` (600 px), uma coluna.
- A cor nunca é o único sinal: todo selo, pill, ponto e cartão selecionado tem texto.
- Nenhuma cor fora de `theme.py`. Contraste de texto de no mínimo 4,5:1 (WCAG AA): todo par
  texto/fundo fica em `theme.PARES_TEXTO`, verificado com `theme.contraste()` em teste. Laranja
  (`COR_DESTAQUE`) nunca é cor de texto pequeno; nada de cinza ou azul claro em texto
  pequeno sobre branco.
- Valores numa linha só (prompt 26): os formatadores de `formatacao.py` unem as partes
  de um valor com espaço que não quebra (U+00A0): 'R$ 1.234,56', '23/11/2026 15:05',
  '3 h 20 min'; duração '2h58' sem espaço; percentual '12,5%' (sem espaço, uma casa, sem
  ',0'). Todo Text que mostra só um valor usa `no_wrap` (`basicos.rotulo_valor(...,
  uma_linha=True)`); faltando espaço, quebra o rótulo, nunca o valor.
- Números alinhados à direita, com o cabeçalho alinhado igual. Tabela de custos com
  proporções fixas 40/20/20/20 (`ui/tabela_custos.py`); abaixo de 600 px, um cartão por
  categoria e o Total por último, destacado.
- Textos de diferença numa só função (`ui/historico.py`): 'R$ 120,00 acima do previsto
  (+12%)', 'R$ 120,00 abaixo do previsto (−12%)', '2h58 abaixo do previsto', 'Igual ao
  previsto'. O percentual leva o sinal; o valor, não; nunca sinal de menos junto das
  palavras; sem previsto, sem percentual. Nas linhas de categoria só valor e percentual,
  com a etiqueta 'acima'/'abaixo'; as palavras ficam no Total.
- Histórico: todo `campo` de os_eventos tem rótulo em `ui/rotulos_eventos.py` (inclusive
  os legados); campo desconhecido aparece como 'Campo alterado' e gera aviso no log.
- Números da faixa e do selo vêm de `services.ordens.contadores` (mesmo escopo de filial de
  `listar_os`); atualizados em 'Atualizar' e depois de cada mudança de status na sessão.

## Fora do escopo do MVP (o desenho não pode bloqueá-los)

Status cancelada, triagem, aceite pela operação, KPIs, fotos, notificações (exceto o e-mail
de nova solicitação, abaixo), planos preventivos, estoque, exportação PDF/Excel.

## Notificações por e-mail (prompt 32; substitui a regra do prompt 20 'sem e-mail')

- E-mail só para **manutenção** e **administrador**, opcional e com consentimento (LGPD): o
  endereço é gravado só por ação do próprio usuário, serve só para estes avisos e o próprio
  usuário o remove ('Remover e-mail'). O papel usuario não tem campo de e-mail (o serviço
  recusa). O administrador vê o endereço na tela do usuário e pode desligar as notificações
  dele, mas nunca grava nem confirma endereço de outra pessoa.
- Confirmação por código de 6 dígitos (`secrets`); só o HMAC (OS_HMAC_SEGREDO) é gravado.
  Validade de 15 min, 5 erros exigem código novo, um código a cada 60 s e no máximo 5 por
  hora por usuário. Endereço não confirmado nunca recebe aviso; trocar o endereço apaga a
  confirmação. Notificações começam desligadas.
- Único evento: solicitação nova (status Aberta, origem 'solicitacao'). Destinatários:
  ativos, manutenção ou administrador, endereço confirmado, notificações ligadas, filial
  da OS acessível (administrador: todas; manutenção: a própria — até o prompt 28) e
  urgência da OS >= urgência mínima (baixa < media < alta < emergencial). O solicitante
  não é avisado do próprio pedido.
- **Caixa de saída transacional**: o serviço só grava linhas em `email_fila`, na mesma
  transação da OS; nada fala com o SMTP durante um pedido. Um trabalhador por processo
  (iniciado no on_startup do app ASGI, nunca no `main()` do Flet) envia, com reserva
  atômica (PostgreSQL: FOR UPDATE SKIP LOCKED), concessão de 5 min, novas tentativas
  exponenciais (1, 2, 4... até 60 min) e 'falhou' depois de OS_EMAIL_MAX_TENTATIVAS.
  Entrega pelo menos uma vez; Message-ID estável pelo id da linha.
- Mensagem: só texto puro UTF-8 (`EmailMessage`). Texto de usuário só no Assunto (limpo de
  CR, LF e controles, 150 caracteres) e no corpo; nunca em outro cabeçalho. Nunca custos,
  previsto, realizado, prioridade, executor nem histórico. Logs com o id da linha e o
  endereço mascarado (j***@dominio), nunca o endereço inteiro nem o corpo.
- SMTP só por variáveis de ambiente (OS_SMTP_*); sem elas os avisos ficam pendentes.
  Retenção: `limpar-fila-email` (enviados/cancelados 30 dias, falhos 90). Nada de HTML,
  outros eventos ou outros canais. Testes nunca usam SMTP real.

## Busca e cadastro de equipamento (prompt 21)

- Não existe cadastro de equipamento: o que foi atendido é descrito pelos itens de custo
  (peça, mão de obra, terceiros...). `numero_sap` continua na OS para a integração futura.
- Busca sem diferença de maiúsculas e acentos: o texto gravado (`busca_texto`) e o termo
  digitado passam pela mesma `osapp.busca.normalizar_busca`. Nada específico de um banco
  (nem `unaccent`, nem índice trigram por enquanto): o mesmo código no SQLite e no
  PostgreSQL.
- `busca_texto` é mantido por eventos do ORM: nunca usar inserção ou alteração em lote em
  `ordens_servico` e `os_itens_custo`.

## 'Lembrar de mim por 7 dias' (prompt 35; exceção à regra do prompt 6)

- A regra do prompt 6 'nunca guardar token no armazenamento do navegador' continua valendo,
  com UMA exceção: o token 'Lembrar de mim', guardado com `ft.SharedPreferences` (chave
  `osapp.lembrar`) só quando o usuário marca a caixa (desmarcada por padrão; dica 'Não
  marque em aparelhos compartilhados.').
- Como qualquer um com acesso ao navegador lê o token, a proteção é do servidor
  (`services/sessoes_lembradas.py`): 32 bytes do `secrets`; só o SHA-256 no banco; nunca
  em log; validade de 7 dias desde o login, que a rotação não estende; troca a cada uso
  (mesma família, mesmo `expira_em`); token já trocado usado de novo revoga a família e
  gera aviso de segurança no log; toda recusa é igual e conta no limite por IP;
  revogação em 'Sair', 'Sair de todos os aparelhos', troca e redefinição de senha,
  desativação e pelo administrador. `rotulo_aparelho` é um texto curto, nunca o user
  agent cru nem o IP.
- Sem a caixa, o tempo de inatividade continua o mesmo. Com ela, uma sessão expirada é
  retomada pelo token, dentro dos 7 dias.

## Escopo e especialidade (prompt 37)

- O sistema é só de **manutenção** (mecânica, elétrica, predial/civil, utilidades). **TI
  está fora do escopo**: pedidos de informática não entram aqui.
- Toda OS ganha a especialidade que a atende (tabela `especialidades`, mantida pelo
  administrador em Perfil > Especialidades; desativada não entra em OS nova e continua
  nas antigas). Definida por manutenção (de uma filial permitida) ou administrador, como
  tipo e prioridade; obrigatória para iniciar (`pendencias_para_iniciar`). O papel
  usuario nunca define nem recebe a especialidade (fora de `OsVisaoSolicitante` e
  `ResumoSolicitante`).
- Usuários de manutenção podem ter zero ou mais especialidades (`usuario_especialidades`);
  hoje isso não filtra nada (prepara o filtro de avisos). Mudar o papel as apaga.

## SLA (prompt 38)

- Alvos por filial e urgência em `sla_alvos` (minutos de relógio; um dia = 24 h; sem dias
  úteis nesta versão). Padrões: emergencial 1 h / 8 h, alta 4 h / 2 dias, média 1 dia /
  5 dias, baixa 3 dias / 15 dias. Filial nova recebe os padrões. Só o administrador
  altera (Perfil > SLA), com registro no log.
- Os prazos são gravados na OS ao abrir (`prazo_inicio_em`, `prazo_solucao_em`), com os
  alvos daquele momento; mudar a urgência com a OS ABERTA recalcula os dois (evento
  EDICAO). Mudar os alvos nunca muda ordens existentes. Só ordens com urgência
  (solicitações) têm prazo.
- Etiqueta calculada no serviço (`services/sla.etiqueta`): ABERTA usa o prazo de início,
  EM_EXECUCAO o de solução; 'Atrasada' / 'Vence em X' (25% ou menos restando) / 'No
  prazo', sempre com texto e ícone. Só manutenção e administrador recebem; o usuario não.
- Relatório: % dentro do SLA de início e de solução entre as ordens já vencidas no fim do
  período ou que já cumpriram a etapa (as que ainda estão no prazo ficam fora do
  denominador), com a situação reconstruída no fim do período (prompt 25); '—' com
  denominador zero; também por urgência.

## Ajustes do prompt 41

- **Apagamento físico**: a regra continua 'nunca apagar' (exclusão lógica, prompt 24), com
  UMA exceção: o comando `preparar-piloto`, só para o reinício antes do piloto. Ele apaga
  as OS de teste e o que depende delas (itens, eventos, fila de e-mails, 'lembrar de mim',
  contadores de login) e reinicia a numeração; exige `--confirmar`, o nome do banco
  digitado e, com `OS_AMBIENTE=producao`, `--sei-que-e-producao`. Sempre depois de um
  backup.
- Seção de itens de custo única (`SecaoItensCusto`, `components/editor_itens.py`) nas
  três telas (previsto em Nova OS e Alterar, realizado em Concluir), com as regras de
  'Sem gasto' do prompt 31 em `EstadoFase`. 'Sem gasto' existe também na criação
  (`criar_os(..., sem_gasto_previsto=True)`, recusado junto com itens).
- Exibição de uma fase (`ui/fase_custo.py`): sem item e sem marca, 'A DEFINIR' e '—'
  (nunca 'R$ 0,00' para 'não preenchido'); marcada, 'SEM GASTO'; com itens, o total.
- `ordens.pendencias_inicio` é a única lista do que falta para iniciar, usada pelo
  serviço e pela tela; no Detalhe, 'Iniciar execução' fica visível e desabilitado, com os
  motivos e atalhos.
- Faixa: 'Abertas' (status Aberta) e 'Em execução'; o selo de Ordens mostra as Abertas.
  Filtro rápido 'Abertas pela operação' (solicitações Abertas, por urgência e idade).
- Cancelamento com motivo obrigatório (`motivos_cancelamento`, editável pelo
  administrador; 'Outro' exige 5 a 300 caracteres); o motivo vai no evento e aparece no
  Detalhe para todos que veem a OS.
- Barra inferior própria (`components/barra_inferior.py`), centralizada na largura do
  conteúdo, abaixo da área rolável (o conteúdo nunca fica por baixo dela).
