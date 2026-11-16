# Estado do projeto

Registro corrente do que existe e de como executar. Cada prompt atualiza este arquivo.

## Prompt 1 — esqueleto, tema, página de fumaça

### O que existe

- `pyproject.toml`: pacote `osapp` (layout `src/`), `flet[web]>=1.1,<1.2`, `python-dotenv`;
  extras de desenvolvimento `pytest` e `ruff`. Versão do Flet verificada: 1.1.2.
- `src/osapp/config.py`: `carregar_config(env=None) -> Config` (`database_url`, `tz`,
  `sessao_timeout_min`, `log_level`); `ConfigError` com mensagem clara. Lê `.env` local via
  python-dotenv. Não há URL de banco padrão no código.
- `src/osapp/formatacao.py` (sem Flet, sem locale): `formatar_brl`, `ler_brl`, `formatar_data`,
  `formatar_data_hora`, `formatar_duracao`, `ler_duracao`.
- `src/osapp/ui/theme.py`: todos os tokens de cor, raio e tamanho; `criar_tema()`,
  `aplicar_tema(page)`, `estilo_botao_primario()`.
- `src/osapp/ui/components/cabecalho.py`: `cabecalho(nome, codigo_filial, on_voltar, on_menu)`.
- `src/osapp/main.py`: página de fumaça (`main(page)`), `construir_conteudo_smoke()` e o objeto
  ASGI `app`.
- Pacotes vazios: `models/`, `repositories/`, `services/`, `ui/views/`.
- Testes: `tests/test_formatacao.py`, `tests/test_config.py`, `tests/test_tema.py`.

### Como executar

```bash
pip install -e '.[dev]'
cp .env.example .env
python -m osapp.main                                  # desenvolvimento, http://localhost:8550
uvicorn osapp.main:app --host 0.0.0.0 --port 8000     # produção (ASGI)
ruff check . && pytest -q
```

### Decisões

- A dependência é `flet[web]` (extra oficial do próprio Flet, que traz `flet-web`, FastAPI e
  uvicorn): sem ela o Flet não serve a aplicação web nem exporta o app ASGI.
- `formatar_data` e `formatar_data_hora` tratam datetime sem fuso como UTC e convertem para
  `OS_TZ`; um `date` puro é formatado sem conversão. Ambas aceitam `tz=` opcional.
- `ler_brl` é estrito: exige vírgula e dois decimais (`1234`, `12,3` e negativos são rejeitados).
- `formatar_brl` aceita negativos (`-R$ 1.234,56`), úteis para diferenças.
- Os botões de voltar e de menu do cabeçalho ainda não fazem nada.

### Lacunas conhecidas

- Sem banco, login, rotas ou telas reais (prompts seguintes).
- `OS_DATABASE_URL` é validada apenas quanto à presença; nada se conecta ao banco ainda.
- `OS_SESSAO_TIMEOUT_MIN` é lida, mas ainda não é usada.
- Verificação visual feita com Chromium headless a 390 px e 1280 px; não testado em aparelho real.

## Prompt 2 — modelos, migração, repositórios

### O que existe

- Dependências novas: `sqlalchemy>=2`, `alembic`.
- `src/osapp/db.py`: `Base` (MetaData com convenção de nomes), `criar_engine(url)`,
  `obter_engine()`, `obter_fabrica_de_sessoes()`, `reiniciar()` (testes) e o gerenciador de
  contexto `sessao()` (commit no sucesso, rollback no erro). No SQLite, cada conexão liga
  `PRAGMA foreign_keys=ON` e recebe um `lower()` que entende acentos.
- `src/osapp/models/tipos.py`: `DataHoraUTC`, usado em todo timestamp (grava em UTC, lê com
  fuso UTC, recusa datetime sem fuso).
- Modelos: `Filial` (`filiais`), `Usuario` (`usuarios`), `OrdemServico` (`ordens_servico`),
  `OsEvento` (`os_eventos`), com os índices e check constraints pedidos.
- `alembic.ini` + `migrations/` (`env.py` lê a URL de `osapp.config`, `render_as_batch=True`)
  e a migração inicial `0001`.
- Repositórios (recebem uma `Session`; sem regra de negócio nem permissão):
  - `FilialRepo`: `obter`, `obter_por_codigo`, `listar`, `adicionar`.
  - `UsuarioRepo`: `obter`, `obter_por_login`, `adicionar`.
  - `OrdemServicoRepo`: `obter`, `adicionar`,
    `listar(filial_id, status, busca, limite, deslocamento)`, `proximo_numero(ano)`.
  - `OsEventoRepo`: `adicionar`, `listar_por_os` (somente inserção).
- Testes: `tests/conftest.py` (fixtures `banco_vazio` e `banco`), `tests/fabricas.py`,
  `tests/test_migracao.py`, `tests/test_modelos.py`, `tests/test_repositorios.py`.

### Como executar

```bash
OS_DATABASE_URL=sqlite:///./dev.db alembic upgrade head
pytest -q                                   # SQLite temporário por teste
OS_TEST_DATABASE_URL=... pytest -q          # mesmos testes em outro banco
```

### Decisões

- `versao` é o `version_id_col` do mapeamento de `OrdemServico`: o ORM põe
  `WHERE versao = ?` em cada UPDATE, incrementa o valor e levanta `StaleDataError` se outra
  transação gravou antes. Sem alteração real não há UPDATE nem incremento.
- `Usuario.login` é convertido para minúsculas no próprio modelo (`@validates`).
- `criado_em`, `atualizado_em` e `os_eventos.data_hora` têm como padrão o instante atual em
  UTC; os serviços podem informar o valor explicitamente.
- `proximo_numero` usa o maior número existente do ano + 1 (sem sequences do banco).

### Lacunas conhecidas

- Não testado em PostgreSQL neste ambiente (nenhum driver PostgreSQL é dependência do projeto;
  será preciso adicionar um, por exemplo `psycopg`, quando o PostgreSQL entrar).
- No PostgreSQL a busca sem diferenciar maiúsculas depende do `lower()` do banco (correto com
  uma collation UTF-8). A busca diferencia acentos ('balanca' não encontra 'balança').

## Prompt 3 — autenticação, permissões, seed, CLI

### O que existe

- Dependência nova: `argon2-cffi`.
- `services/erros.py`: `ErroDominio`, `ErroValidacao(campo, mensagem)`, `ErroAutenticacao`,
  `ErroPermissao`, `ErroNaoEncontrado`, `ErroConflito`.
- `services/relogio.py`: `agora()` (UTC; os testes substituem `relogio.agora`).
- `services/senhas.py`: `gerar_hash`, `verificar`, `precisa_rehash` (argon2id, parâmetros
  padrão da biblioteca); `SENHA_MIN = 8`, `SENHA_MAX = 128`.
- `services/auth.py`: `Ator`, `autenticar(login, senha)`, `carregar_ator(usuario_id)`.
  5 falhas seguidas bloqueiam por 15 minutos; toda falha levanta o mesmo `ErroAutenticacao`.
- `services/permissoes.py`: `exigir_admin(ator)`, `pode_acessar_filial(ator, filial_id)`.
- `services/administracao.py` (usado só pelo seed e pela CLI, sem ator): `criar_filial`,
  `criar_usuario`, `redefinir_senha`, `desativar_usuario`, `validar_senha`.
- `osapp/logs.py`: `configurar_logging()` a partir de `OS_LOG_LEVEL` (usado por `main.py`,
  seed e CLI).
- `osapp/seed.py` e `osapp/cli.py`.
- Testes: `tests/test_auth.py`.

### Como executar

```bash
alembic upgrade head
OS_SEED_SENHA='<senha de 8+ caracteres>' python -m osapp.seed
python -m osapp.cli criar-filial --codigo F003 --nome 'Filial Modelo Oeste'
python -m osapp.cli criar-usuario          # pergunta nome, login, filial e senha
python -m osapp.cli criar-usuario --nome 'Ana Modelo' --login ana.modelo --filial F001 [--admin]
python -m osapp.cli redefinir-senha --login ana.modelo
python -m osapp.cli desativar-usuario --login ana.modelo
```

### Decisões

- Login ou senha vazios, longos demais ou de tipo errado levantam `ErroAutenticacao` (não
  `ErroValidacao`), antes de qualquer hash e sem tocar no banco.
- Usuário inativo ou bloqueado: a senha ainda é verificada (tempo de resposta uniforme), mas
  a tentativa não altera contadores. Vencido o bloqueio, a contagem recomeça do zero.
- O seed não altera registros existentes (não troca a senha de quem já existe).
- `redefinir-senha` também zera as tentativas e remove o bloqueio.
- `main.py` passou a usar `configurar_logging` (única alteração em arquivo do prompt 1).

### Lacunas conhecidas

- **PENDENTE DE DECISÃO (modelo):** `valor_previsto_centavos` e `valor_realizado_centavos`
  são `Integer`. No PostgreSQL isso é um inteiro de 32 bits (máximo 2.147.483.647 centavos,
  cerca de R$ 21,4 milhões), menor que o limite de negócio de 9.999.999.999 centavos. No
  SQLite não há problema. Antes de usar PostgreSQL é preciso trocar as duas colunas para
  `BigInteger` (modelo + migração). Não foi alterado porque os prompts 3 a 5 proíbem mexer
  em modelos e migração.
- Não há comando para reativar usuário nem para listar usuários.
- A política de senha é só o tamanho (8 a 128 caracteres).
- Não há limitação de tentativas por endereço IP, apenas por usuário.

## Prompt 4 — serviço de OS, parte 1

### O que existe

- `services/status.py`: `ABERTA`, `EM_EXECUCAO`, `CONCLUIDA`, `STATUS_INICIAL`, `ROTULOS`,
  `rotulo(status)`, `status_conhecido(status)`.
- `services/ordens.py` (toda função começa por `carregar_ator(ator_id)` e devolve DTOs):
  - `criar_os(ator_id, titulo, descricao, valor_previsto_centavos, tempo_previsto_minutos,
    filial_id=None) -> OsDetalhe`
  - `obter_os(ator_id, os_id) -> OsDetalhe`
  - `listar_os(ator_id, busca=None, status=None, filial_id=None, pagina=1) -> PaginaOs`
  - `listar_eventos(ator_id, os_id) -> list[EventoDTO]` (do mais antigo ao mais novo)
  - `listar_filiais(ator_id) -> list[FilialDTO]`
  - `registrar_evento(...)`: único ponto que grava em `os_eventos`, na mesma transação.
  - DTOs: `OsDetalhe`, `OsResumo`, `PaginaOs`, `EventoDTO`, `FilialDTO`.
  - Tipos de evento: `TIPO_CRIACAO`, `TIPO_EDICAO`, `TIPO_STATUS`.
- Testes: `tests/test_ordens_parte1.py` (64 testes) e a fixture `cenario` em `conftest.py`.

### Decisões

- O ano do número (`OS-AAAA-NNNNNN`) é o ano no fuso `OS_TZ`, não em UTC. A sequência é única
  por ano para todas as filiais.
- Em conflito de número: 1 tentativa + 3 repetições; depois, `ErroConflito`.
- `titulo` e `descricao` são gravados sem espaços nas pontas; descrição só de espaços é recusada.
- `busca` maior que 100 caracteres é cortada em 100 (não gera erro).
- Um `os_id` de tipo errado é tratado como OS inexistente (`ErroNaoEncontrado`).
- Admin criando em filial inexistente recebe `ErroValidacao("filial_id")`.

### Lacunas conhecidas

- Sem edição, mudança de status nem conclusão (prompt 5).

## Prompt 5 — serviço de OS, parte 2

### O que existe

- `services/status.py`: tabela `TRANSICOES` (`(origem, destino) -> quem pode`),
  `QUALQUER_USUARIO_DA_FILIAL`, `SOMENTE_EXECUTOR`, `quem_pode_transicionar(origem, destino)`,
  `ENCERRADOS` e `encerrado(status)`.
- `services/ordens.py`, funções novas (todas com `versao` para a trava otimista):
  - `editar_os(ator_id, os_id, versao, alteracoes: dict) -> OsDetalhe`
  - `iniciar_execucao(ator_id, os_id, versao) -> OsDetalhe`
  - `desfazer_inicio(ator_id, os_id, versao) -> OsDetalhe`
  - `concluir_os(ator_id, os_id, versao, valor_realizado_centavos, inicio_realizado,
    fim_realizado, descricao_realizado) -> OsDetalhe`
- `OsDetalhe` ganhou `tempo_realizado_minutos`, `diferenca_valor_centavos`,
  `diferenca_valor_percentual`, `diferenca_tempo_minutos` e `acoes: AcoesOs` (`pode_editar`,
  `pode_iniciar`, `pode_desfazer_inicio`, `pode_concluir`, `pode_editar_realizado`).
- Constantes: `CAMPOS_PREVISTO`, `CAMPOS_REALIZADO`, `CAMPO_FILIAL`, `TIPO_REALIZADO`.
- Testes: `tests/test_ordens_parte2.py` (166 testes; a matriz de permissões tem 72 células:
  6 atores x 4 ações x 3 status).

### Decisões

- Ordem das verificações em toda escrita: visibilidade (`ErroNaoEncontrado`) -> permissão
  e transição (`ErroPermissao`) -> versão (`ErroConflito`) -> validação (`ErroValidacao`).
- Transição fora da tabela levanta `ErroPermissao`, inclusive para administrador.
- A conclusão grava um evento `STATUS` e quatro eventos de tipo `REALIZADO` (um por campo,
  `valor_antigo` nulo). Correções posteriores do administrador são eventos `EDICAO`.
- No histórico, instantes são texto ISO 8601 em UTC, inteiros são texto decimal, e a mudança
  de filial registra o código da filial (não o id).
- `diferenca_valor_percentual` é arredondada para 2 casas.
- `tempo_realizado_minutos` é a diferença entre fim e início, em minutos inteiros.
- A OS é gravada uma única vez por operação: `versao` sobe exatamente 1.
- Escrita concorrente detectada pelo banco (`StaleDataError`) também vira `ErroConflito`.

### Lacunas conhecidas

- Se o administrador mudar a filial de uma OS em execução, o executor (da filial antiga)
  deixa de vê-la; o administrador pode concluir ou desfazer o início.
- `inicio_realizado` pode ser anterior à criação da OS (não há regra sobre isso).

## Prompt 6 — casca da interface: login, sessão, guarda de rotas, navegação

### O que existe

- `ui/rotas.py` (puro): tabela central `TABELA` (`/login`, `/`, `/os/nova`, `/os/{id}`,
  `/os/{id}/editar`, `/os/{id}/concluir`), `resolver`, `normalizar` (rota desconhecida -> `/`),
  `rota_anterior`, `rota_os`, `rota_editar`, `rota_concluir`.
- `ui/sessao.py` (puro): `SessaoUI` (ator_id, última atividade, dados de exibição, rota
  pendente), `decidir_rota(rota, sessao, agora)`, `expirada`, `autenticada`, `iniciar`,
  `encerrar`, `registrar_atividade`, `aplicar_navegacao`.
- `ui/app.py`: classe `App` (uma por sessão de navegador): guarda de rotas, casca com
  cabeçalho + navegação, `ir`, `voltar`, `sair`, `entrar`, `avisar` e `chamar` (auxiliar
  único de chamada de serviços, que devolve `Resultado`).
- `ui/views/login.py`, `ui/views/em_construcao.py` (telas provisórias), `ui/views/base.py`.
- `ui/components/basicos.py` (cartão, campo de texto, botões, indicador de carga) e
  `ui/components/cabecalho.py` (agora com `logo`, `barra`, `saudacao`, menu com "Sair").
- `main.py`: `main(page)` cria um `App` por sessão. A página de fumaça foi substituída.
- Testes: `tests/test_ui_rotas_sessao.py`.

### Abordagem de rotas escolhida

A imperativa do cookbook "Navigation and routing": `page.on_route_change` reconstrói
`page.views` a partir de `page.route`; a navegação usa o assíncrono `page.push_route()`.
Cada rota monta uma única `View`. Não se usa o `Router` declarativo (é para apps escritos
com `@component`). O botão de voltar do cabeçalho leva à tela anterior na hierarquia
(`rota_anterior`); o voltar do navegador muda a URL e passa pela mesma guarda.

### Sessão, tempo limite e atualização da página

- O estado da sessão (`SessaoUI`) fica na memória do servidor, dentro do `App` da sessão
  Flet. Nada é gravado no armazenamento do cliente pelo app.
- `OS_SESSAO_TIMEOUT_MIN` minutos sem atividade (navegação ou chamada de serviço) encerram
  a sessão; a próxima navegação ou ação mostra `/login` com "Sessão expirada. Entre
  novamente.".
- **Atualizar a página (F5):** o cliente Flet reconecta à mesma sessão do servidor, então o
  usuário continua logado e na mesma rota (verificado). O próprio Flet mantém uma sessão
  desconectada por `FLET_SESSION_TIMEOUT` segundos (padrão 3600) antes de descartá-la;
  depois disso, ou se o processo reiniciar, a atualização cria uma sessão nova e mostra o
  login. O tempo limite de inatividade do app continua valendo durante a reconexão.
- Abrir o app em outra aba cria outra sessão (novo login).

### Como executar

```bash
alembic upgrade head && OS_SEED_SENHA='<senha>' python -m osapp.seed
python -m osapp.main        # http://localhost:8550 ; entre com marina.teste ou admin
```

### Decisões

- Serviços (bloqueantes) rodam com `await asyncio.to_thread(...)`, como recomenda o
  cookbook "Async apps".
- Navegação: `NavigationBar` abaixo de 600 px, `NavigationRail` a partir de 600 px, trocando
  em `page.on_resize`.
- Ferramentas oficiais de teste do Flet (`flet test` / `flet.testing`): **não rodam neste
  ambiente** (`import flet.testing` falha por falta de numpy; o extra `flet[test]` traz
  numpy, pillow e scikit-image e o executor precisa do cliente Flutter de desktop). Não há
  teste de integração Flet; a verificação foi feita dirigindo o app em Chromium headless
  (Playwright) a 390 px e 1280 px.

### Lacunas conhecidas

- Sem telas reais de Home, Detalhe e formulários (prompts 7 a 9).
- Um usuário desativado só é barrado na próxima chamada de serviço (as telas provisórias
  não chamam serviços).

## Prompt 7 — Home (lista) e Detalhe da OS

### O que existe

- `ui/views/home.py` (`/`): busca (Enter ou ícone), chips de status (Todas + os status de
  `services/status.py`), lista de filiais só para administrador ("Todas as filiais" + cada
  filial, começando na própria), botão "Atualizar", cartões das OS, "Carregar mais", estado
  vazio "Nenhuma OS encontrada." e indicador de carga.
- `ui/views/detalhe.py` (`/os/{id}`): topo, cartões "Previsto", "Realizado", "Diferença" (só
  quando concluída) e "Histórico" (do mais novo ao mais antigo); "OS não encontrada." com
  botão para a lista.
- `ui/historico.py` (puro): `CAMPOS` (campo -> rótulo e formatador), `frase(evento)`,
  `comparacao`, `texto_diferenca_valor`, `texto_diferenca_tempo`.
- `ui/components/basicos.py`: `selo_status`, `rotulo_valor`, `mensagem_central`.
- Testes: `tests/test_ui_historico.py`.

### Como criar dados de demonstração

Depois do seed, um script curto que chame `auth.autenticar` e `ordens.criar_os`,
`iniciar_execucao` e `concluir_os` cria OS nas duas filiais (não há script no repositório).

### Decisões

- A tela não filtra por filial nem decide permissão: passa os filtros ao serviço e mostra o
  que ele devolve. O filtro de filial só aparece para administrador (dado de exibição da
  sessão); para os demais a tela envia `filial_id=None` e o serviço restringe.
- Frases do histórico usam `->` e cortam textos longos em 80 caracteres.
- Diferenças mostram sinal, percentual com uma casa e as palavras "Acima do previsto",
  "Abaixo do previsto" ou "Igual ao previsto".

### Lacunas conhecidas

- Sem botões de criar, alterar ou mudar status (prompts 8 e 9).
- O histórico não é paginado.

## Prompt 8 — Criar OS e Alterar OS

### O que existe

- `ui/formularios.py` (puro): `ler_valor`, `ler_tempo`, `tempo_para_campo`, `valor_para_campo`,
  `ler_data`, `ler_hora`, `para_utc`, `ler_data_hora`, `partes_locais`, `somente_alterados`.
- `ui/components/formulario_os.py`: `FormularioOs`, o formulário único das duas telas
  (título, descrição, valor previsto, tempo previsto, filial; e os campos de "realizado"
  quando `acoes.pode_editar_realizado`).
- `ui/views/os_formulario.py`: `CriarOs` (`/os/nova`, botão "Salvar OS") e `EditarOs`
  (`/os/{id}/editar`, botão "Salvar alterações", envia a `versao` carregada).
- Detalhe: botão "Alterar" quando `acoes.pode_editar`.
- `App`: confirmação "Descartar alterações?" ao sair de um formulário alterado (navegação do
  app, botão voltar do cabeçalho e botão voltar do navegador); textos do Material em pt-BR
  (`page.locale_configuration`).
- Testes: `tests/test_ui_formularios.py`.

### Decisões

- Alterar envia ao serviço só os campos que mudaram (assim um usuário comum nunca envia
  `filial_id`). Sem mudança, volta ao Detalhe com "Nenhuma alteração para salvar.".
- Rota `/os/{id}/editar` aberta sem permissão: a tela usa `acoes.pode_editar` (calculado
  pelo serviço) e mostra a mensagem genérica, sem o formulário. Se o formulário for
  enviado mesmo assim, o serviço recusa.
- Datas e horas do "realizado" são campos de texto (`dd/mm/aaaa` e `HH:MM`) no fuso `OS_TZ`.
- O valor exige vírgula e dois decimais (`ler_brl` é estrito): "150" é recusado com a
  mensagem "Valor inválido. Use o formato 1.234,56.".
- Sair para `/login` (logout ou sessão expirada) não pede confirmação.

### Lacunas conhecidas

- Sem botões de status nem tela de conclusão (prompt 9).
- O teclado numérico de alguns celulares pode não ter vírgula ou dois-pontos; o tipo de
  teclado é só uma sugestão ao navegador (não verificado em aparelho real).
- Se a sessão expirar com o formulário aberto, o que foi digitado é perdido.

## Prompt 9 — ações de status, Concluir OS, auditoria, README

### O que existe

- Detalhe: botões "Iniciar execução" e "Desfazer início" (com diálogo de confirmação) e
  "Concluir OS", mostrados conforme `acoes`; quando em execução, mostra quem iniciou e quando.
- `ui/views/concluir.py` (`/os/{id}/concluir`): resumo do previsto, valor realizado, início
  e fim (data + hora), descrição do que foi feito, prévia ao vivo das diferenças e botão
  "Concluir OS".
- `ui/formularios.py`: `previa_diferencas`.
- `App.confirmar`: diálogo de confirmação reutilizável.
- `docs/AUDITORIA.md`, `docs/PROXIMOS_PASSOS.md` e o `README.md` final.
- Todas as rotas têm tela real; a tela provisória "Em construção" foi removida.
- Suíte: 523 testes.

### Decisões

- Início e fim são campos de texto (`dd/mm/aaaa` e `HH:MM`), com a data de hoje preenchida.
  Os seletores `DatePicker` e `TimePicker` do Flet existem, mas são diálogos em tela cheia
  e exigiriam quatro aberturas por conclusão; campos de texto são mais rápidos no celular
  e têm mensagens de erro claras.
- As horas são digitadas no fuso `OS_TZ` e convertidas para UTC antes de chamar o serviço.
- A prévia das diferenças é só visual; os números oficiais vêm do serviço.
- Rota `/os/{id}/concluir` aberta sem permissão mostra a mensagem genérica (usa
  `acoes.pode_concluir`, calculado pelo serviço).

### Verificação manual (Chromium headless, 390 px e 1280 px)

Roteiro do prompt 9 executado de ponta a ponta: marina cria; joão inicia; marina não vê
"Concluir OS" nem "Desfazer início"; joão desfaz e inicia de novo; joão conclui com 13:50
a 14:30 (o serviço recusou a data de hoje por estar no futuro e aceitou a de ontem); marina
não edita mais e o administrador edita, com a mudança no histórico; carlos (F002) recebe
"OS não encontrada."; a sessão expira depois do tempo limite.

### Lacunas conhecidas

- Pendência de modelo antes do PostgreSQL: colunas de valor em `BigInteger`
  (ver `docs/AUDITORIA.md`, item d).
- Não testado em PostgreSQL, nem em celular real, nem com as ferramentas `flet test`.
- Sem limite de tentativas de login por endereço IP.
- Funcionalidades adiadas: ver `docs/PROXIMOS_PASSOS.md`.
