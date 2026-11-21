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
  Nunca recebe previsto, realizado, custos, equipamento, tipo, prioridade, executor nem o
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

## Fora do escopo do MVP (o desenho não pode bloqueá-los)

Status cancelada, triagem, aceite pela operação, KPIs, fotos, notificações, planos preventivos,
estoque, exportação PDF/Excel.

## Busca e cadastro de equipamento (prompt 21)

- Não existe cadastro de equipamento: o que foi atendido é descrito pelos itens de custo
  (peça, mão de obra, terceiros...). `numero_sap` continua na OS para a integração futura.
- Busca sem diferença de maiúsculas e acentos: o texto gravado (`busca_texto`) e o termo
  digitado passam pela mesma `osapp.busca.normalizar_busca`. Nada específico de um banco
  (nem `unaccent`, nem índice trigram por enquanto): o mesmo código no SQLite e no
  PostgreSQL.
- `busca_texto` é mantido por eventos do ORM: nunca usar inserção ou alteração em lote em
  `ordens_servico` e `os_itens_custo`.
