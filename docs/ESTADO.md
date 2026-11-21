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

## Depois do prompt 9

- `executar.sh`: prepara o ambiente (venv, dependências, `.env`, migração, seed opcional) e
  inicia o app em desenvolvimento com um comando. Testado em uma cópia limpa do projeto.

## Nuvem e PostgreSQL

- Migração `0002`: `valor_previsto_centavos` e `valor_realizado_centavos` em `BigInteger`
  (resolve a pendência do item d da auditoria).
- Extra `postgres` no `pyproject.toml` (`psycopg[binary]`); `config.normalizar_url_do_banco`
  aceita `postgres://` e `postgresql://`; conexões de rede usam `pool_pre_ping` e
  `pool_recycle`.
- `Dockerfile`, `.dockerignore`, `docker/iniciar.sh` (migração, seed opcional, uvicorn com
  um processo) e `render.yaml`. Guia em `docs/NUVEM.md`.
- Verificado: a suíte inteira passa em SQLite e em PostgreSQL 16
  (`OS_TEST_DATABASE_URL`); a imagem foi construída e executada contra PostgreSQL, com
  login e criação de OS pelo navegador.
- Não verificado: a implantação real no Render e no Neon (exige contas do responsável).

## Prompt 10 (parcial) — Configurações e rótulos por extenso

Feitos os itens 1 e 3. Os itens 2 (logotipo) e 4 (Relatórios) ficaram pendentes: ver abaixo.

### O que existe

- `ui/textos.py`: os rótulos da tela principal, da navegação, do menu e de Configurações em
  um só módulo. Regra: "Ordem de Serviço" por extenso, nunca a sigla.
- Rota `/configuracoes` (`ui/rotas.py`, `ui/views/configuracoes.py`), atrás da mesma guarda
  das demais. Mostra, só para leitura, em cartões: nome, usuário (login), filial (código e
  nome), perfil (Administrador ou Usuário) e a versão do app.
- Menu do cabeçalho: "Configurações" (engrenagem) acima de "Sair".
- Home: título "Ordens de Serviço"; estado vazio "Nenhuma Ordem de Serviço encontrada.";
  campo de busca com rótulo "Buscar" e dica "Número, título ou descrição".
- Navegação: "Ordens de Serviço" e "Nova Ordem de Serviço" (por extenso na barra inferior;
  em duas linhas no trilho lateral). Título da aba: "Sistema de Ordens de Serviço".
- Testes: `tests/test_ui_textos.py` (inclui o teste que falha se um rótulo da tela principal
  ou da navegação tiver a sigla isolada).

### Decisões

- O login mostrado em Configurações é o que o usuário digitou e o serviço aceitou, guardado
  na sessão (`SessaoUI.login`) no momento do login. Não foi preciso mudar serviços.
- O nome da filial vem de `ordens.listar_filiais` (serviço já existente).
- A versão vem dos metadados do pacote (`pyproject.toml`).
- `theme.LARGURA_TRILHO` passou de 88 para 100 para caber o rótulo em duas linhas.

### Pendências deste prompt

- **Logotipo:** `src/osapp/assets/logo.png` não existe no repositório; o logo provisório
  (ícone + "OS") continua no cabeçalho e no login. É o único "OS" como sigla que resta na
  tela principal.
- **Relatórios:** não existe funcionalidade de relatórios no código; por decisão do
  responsável, o item foi adiado.
- A sigla continua nas telas fora da principal (formulários, Detalhe, mensagens como
  "OS criada."), que estavam fora do escopo.

### Implantação

O serviço no Render tem implantação automática: um `git push` para o ramo publicado
implanta. Este commit foi deixado só no repositório local, sem push.

## Relatórios, perfil gerente e login por extenso (17/11/2026)

### O que existe

- **Perfil gerente:** coluna `usuarios.is_gerente` (migração `0003`), `Ator.is_gerente`,
  `permissoes.pode_ver_relatorio_completo`, `administracao.definir_perfil`, CLI
  `criar-usuario --gerente` e `definir-perfil`. Seed: nova usuária fictícia `gerente.norte`
  (F001). Nas Ordens de Serviço o gerente tem as mesmas permissões do usuário comum.
- **`services/relatorios.py`:** `gerar_relatorio(ator_id, ano, mes, filial_id=None)`, mês no
  fuso `OS_TZ`.
  - Básico (todos, própria filial): OS por status agora, criadas no mês, concluídas no mês,
    tempo médio de execução.
  - Completo (gerente na própria filial; administrador em qualquer filial ou no consolidado):
    valor previsto, gasto total realizado, diferença em R$ e %, tempo previsto e realizado,
    quantas OS passaram do valor previsto, as 5 com maior estouro, desempenho por executor e,
    no consolidado, totais por filial.
- **Tela Relatórios (`/relatorios`):** terceira aba da navegação (barra inferior e trilho),
  item "Relatórios" no menu, seletor de mês e, para administrador, de filial. Para quem não
  pode ver o completo, um cartão avisa que valores e desempenho por pessoa são restritos.
- **Rótulos:** barra inferior com três destinos usa a forma curta por extenso ("Ordens",
  "Nova Ordem", "Relatórios"); o trilho lateral mantém os nomes completos. Tela de login:
  "Ordens de Serviço" por extenso. Configurações mostra o perfil "Gerente".
- **Migrações no SQLite:** `migrations/env.py` desliga as chaves estrangeiras durante a
  migração e confere a integridade no fim (defeito corrigido; ver AUDITORIA, adendo).
- Testes: `tests/test_relatorios.py`, novos casos em `test_auth.py`, `test_migracao.py` e
  `test_ui_textos.py`. A suíte também passa em PostgreSQL 16.

### Decisões

- "Sensível" = valores em dinheiro e dados por pessoa. Contagens e tempo médio são básicos.
- O gasto do mês considera as OS concluídas no mês (pela data de conclusão, no fuso local).
- O executor de uma OS concluída é quem a iniciou; sem ele, quem a concluiu.

### Lacunas conhecidas

- **Logotipo:** o arquivo da Copa Energia ainda não está no repositório; o cabeçalho continua
  com o logo provisório ("OS"), inclusive na aba Relatórios.
- No SQLite, uma migração que falha no meio pode deixar uma tabela `_alembic_tmp_*`; é
  preciso apagá-la antes de tentar de novo. Afeta só o banco local de desenvolvimento.
- Não há tela para mudar perfis; usa-se a CLI.
- Sem exportação PDF/Excel dos relatórios.

## Inicialização simultânea no Render (17/11/2026)

- Duas instâncias subiram juntas numa implantação e ambas rodaram migração e seed. Reproduzido
  localmente: com três instâncias simultâneas, duas falhavam na inicialização.
- O pre-deploy do Render resolveria, mas só existe em planos pagos. Solução gratuita:
  `db.trava_de_inicializacao` (trava consultiva do PostgreSQL) em `migrations/env.py` e no
  seed. Com a trava, 5 de 5 tentativas com três instâncias terminaram sem erro.

## Logotipo da Copa Energia (17/11/2026)

- Arquivo: `src/osapp/assets/logo.png`, a partir da imagem enviada pelo responsável
  (310 x 163 px, fundo branco). Foram cortadas só as margens brancas: 216 x 94 px, pixels
  idênticos aos do original, sem redimensionar nem recolorir.
- `ui/marca.py`: pasta de assets (caminho absoluto dentro do pacote) e o controle do
  logotipo, com rótulo acessível "Copa Energia" e proporções mantidas (`BoxFit.CONTAIN`).
- Cabeçalho escuro: logotipo sobre uma placa branca arredondada (as letras do logotipo são
  escuras e sumiriam no fundo grafite). Altura `theme.ALTURA_LOGO_CABECALHO` (30).
- Login: logotipo (altura 56) e, abaixo, "Ordens de Serviço" por extenso.
- `main.py` passa `assets_dir` ao Flet no desenvolvimento e no ASGI; o `pyproject.toml`
  inclui `assets/*.png` no pacote, que é o que o contêiner instala. Se o arquivo faltar, as
  telas voltam ao logo provisório.
- Lacuna: o arquivo tem 94 px de altura. No login (56 px de tela), celulares de alta
  densidade ampliam a imagem e ela pode ficar levemente menos nítida. Um arquivo maior
  (ou SVG) resolveria.

## Prompt 11 — caracteres quebrados (18/11/2026)

### Diagnóstico

- **Classe B (fonte), confirmada:** o app publicado baixava do Google a fonte Roboto
  (`fonts.gstatic.com`) e o motor gráfico (`www.gstatic.com`). Com a CDN de fontes bloqueada,
  a tela de login ficou **sem nenhum texto**; numa rede 4G simulada com a fonte lenta, o app
  ainda estava na tela de carregamento após 12 s.
- **Classe A (codificação), não encontrada:** arquivos do projeto em UTF-8 válido, toda
  leitura/escrita de arquivo com `encoding` explícito, banco de produção com
  `server_encoding` e `client_encoding` `UTF8` e nenhum texto gravado com padrão de
  mojibake (consulta só de leitura).
- **Classe C, não encontrada:** título da aba, `charset` da página e logs do servidor corretos.
- **Classe D (teclado do celular):** não testável aqui, sem aparelho real; ver o relatório.

### Correção

- Fonte embutida: Roboto estática Regular (400) e Bold (700), recortada para Latim-1, Latim
  Estendido-A e pontuação comum (65 KB cada), em `src/osapp/assets/fonts` com a licença
  `OFL.txt` (SIL OFL 1.1, sem nome reservado). Gerada a partir da fonte variável oficial do
  repositório google/fonts com fontTools (`instancer` + `subset`).
- `theme.FONTE_FAMILIA` / `theme.FONTE_ARQUIVOS`; `aplicar_tema` registra `page.fonts` e o
  tema usa `font_family`.
- `main.py`: `no_cdn=True` no desenvolvimento e no ASGI — o motor (`/canvaskit/`) e as
  fontes passam a vir do próprio app.
- Só o arquivo Regular é registrado: o Flet aceita um arquivo por família, e o negrito
  sintetizado ficou correto nas telas verificadas. O arquivo Bold fica no pacote para quando
  o Flet aceitar pesos por família.
- Testes: `tests/test_caracteres.py`.

### Lacunas

- Continua sendo baixado `rive_native.wasm` de `cdn.jsdelivr.net` (animações Rive, não usadas
  pelo app). Bloqueado, nada mudou nas telas verificadas.

## Prompt 12 — modelo de dados: custos, equipamentos, numeração, SAP (18/11/2026)

### Tabelas e colunas (migração `0004`, com downgrade)

- `categorias_custo` (codigo único, nome, ordem, ativo) com MAO_DE_OBRA, PECAS_MATERIAIS,
  SERVICOS_TERCEIROS e OUTROS inseridas pela migração.
- `os_itens_custo` (os_id com ON DELETE RESTRICT, fase PREVISTO/REALIZADO, categoria,
  descricao, quantidade, valor_unitario_centavos, criado_em, atualizado_em); restrições
  quantidade > 0, valor >= 0, fase válida; índice (os_id, fase). Nenhuma coluna de total.
- `quantidade` usa o tipo `Quantidade` (`models/tipos.py`): NUMERIC(12,2) no PostgreSQL,
  inteiro de centésimos no SQLite; sempre `decimal.Decimal`, recusa float e mais de 2 casas.
- `equipamentos` (filial, nome, codigo_sap, ativo).
- `ordens_servico`: `numero` até 30, `numero_sap` (indexado, não único), `equipamento_id`,
  `equipamento_outro`. As colunas de preço único continuam (os serviços ainda as usam).
- `os_sequencias` (filial_id, ano) -> ultimo_numero.

### Numeração

- `{código da filial}-{ano}-{sequência de 6 dígitos}`, ex. `1007-2026-000001`; uma sequência
  por filial e ano (no fuso `OS_TZ`).
- `OsSequenciaRepo.reservar_proximo`: INSERT ... ON CONFLICT DO NOTHING para criar a linha,
  depois SELECT ... FOR UPDATE e incremento, na mesma transação da OS. Falha = número não
  consumido. A restrição única de `numero` continua como rede de segurança (vira
  `ErroConflito`). OS antigas mantêm o número.
- PostgreSQL: 20 criações simultâneas recebem 20 números distintos e consecutivos (teste).
  SQLite: o teste de concorrência é pulado (o SQLite trava o arquivo inteiro e responde
  "database is locked"; não há FOR UPDATE); a lógica sequencial é testada nos dois.

### Seed e consolidação

- Seed: filial 1007 Jardinópolis, categorias, 3 equipamentos de exemplo e `admin`. Usuários
  fictícios só com `OS_SEED_EXEMPLOS=1`.
- `python -m osapp.cli consolidar-1007` lista (sem alterar) os usuários fictícios a
  desativar e os usuários e OS de outras filiais a mover para 1007; `--aplicar
  --responsavel LOGIN` aplica numa transação, com evento EDICAO de filial em cada OS movida.
  Nada é apagado; as filiais antigas ficam vazias (não há coluna "ativo" em filiais).

### Lacunas

- Itens de custo e equipamentos ainda não têm serviços nem telas (prompts 13 e 14).
- O perfil gerente (pedido em 17/11) continua; o prompt 12 citava só usuário comum e admin.
- `OrdemServicoRepo.proximo_numero` (numeração antiga) ficou sem uso.

## Prompt 13 — itens de custo e equipamentos nos serviços (18/11/2026)

**As telas atuais não funcionam com estes serviços: implantar só junto com o prompt 14.**

### Funções novas

- `services/custos.py`: `ItemEntrada`, `ItemDTO`, `ResumoCustos`, `ResumoCategoria`,
  `total_da_linha` (Decimal, ROUND_HALF_UP), `calcular_resumo(itens)` (puro, sem banco),
  `percentual`, validações, `listar_categorias(ator_id)`, `adicionar_item`, `editar_item`,
  `remover_item`.
- `services/equipamentos.py`: `listar_equipamentos(ator_id, filial_id=None)`,
  `criar_equipamento` e `desativar_equipamento` (administrador, pela CLI).
- CLI: `criar-equipamento --responsavel --filial --nome [--codigo-sap]` e
  `desativar-equipamento --responsavel --id`.
- `formatacao.ler_quantidade` ('1', '1,5', '1,50'; '1.5' recusado) e `formatar_quantidade`.

### Assinaturas que mudaram

- `criar_os(ator_id, titulo, descricao, itens_previstos, tempo_previsto_minutos,
  filial_id=None, *, equipamento_id=None, equipamento_outro=None)`.
- `concluir_os(ator_id, os_id, versao, itens_realizados, inicio_realizado, fim_realizado,
  descricao_realizado)`.
- `editar_os` aceita `equipamento_id` / `equipamento_outro` e recusa campos de dinheiro.
- `OsDetalhe`: saem `valor_previsto_centavos`, `valor_realizado_centavos`,
  `diferenca_valor_*`; entram `equipamento_id`, `equipamento_outro`, `equipamento`,
  `numero_sap`, `itens`, `resumo_custos`; `AcoesOs` ganha `pode_editar_itens_previstos` e
  `pode_editar_itens_realizados`. `OsResumo.total_previsto_centavos` (calculado).
- `formatacao.ler_brl`: '150' passa a valer R$ 150,00 (regra aprovada no prompt 13);
  '150.50' continua recusado.

### Regras

- Itens PREVISTO: criadora ou admin antes da conclusão; depois, só admin. Itens REALIZADO:
  chegam com a conclusão (executor ou admin); depois, só admin. Mínimo de 1 item em cada
  fase; máximo de 100. Cada inclusão, alteração e remoção grava ITEM_ADICIONADO /
  ITEM_ALTERADO / ITEM_REMOVIDO e incrementa a versão da OS.
- Equipamento: exatamente um entre um equipamento ativo da filial da OS e "Outro" (3 a 120
  caracteres). Mudar a filial exige equipamento da nova filial.
- Relatórios passaram a somar os itens de custo (o preço único deixou de existir).

### Migração `0005`

- Cada OS ganha um item PREVISTO (e um REALIZADO, se havia valor realizado) na categoria
  OUTROS, "Valor total (migrado)", quantidade 1. OS sem equipamento recebem
  `equipamento_outro` "Não informado" (a migração registra quantas no log). Depois saem as
  colunas de preço único. O downgrade recria as colunas com a soma dos itens e apaga os
  itens migrados.

### Lacunas

- Interface ainda no modelo antigo (prompt 14).
- Percentuais são calculados em Decimal e entregues como float só para exibição.

## Prompt 14 — máscaras de dinheiro e hora, itens de custo e equipamento na interface (18/11/2026)

**Bloqueio aberto: a máscara reescrita pelo servidor perde dígitos com latência de rede
(ver "Máscaras: comportamento medido"). Não implantar sem decidir a alternativa.**

### O que existe

- `ui/mascaras.py` (puro): `mascara_dinheiro`, `mascara_hora` (duração até 999 h e hora de
  relógio 00:00–23:59), `editar_digitos` (dígitos novos entram pela direita onde quer que
  esteja o cursor; apagar tira o último dígito; substituir tudo fica com os dígitos colados).
- `ui/components/campos.py`: `CampoDinheiro` (prefixo R$, centavos), `CampoDuracao`
  (minutos) e `CampoHora` (`datetime.time`). A cada mudança o campo reescreve o texto e põe
  o cursor no fim; ao focar ou tocar no campo, o cursor também vai para o fim.
- `ui/components/editor_itens.py`: editor de uma fase, itens agrupados por categoria,
  subtotal por categoria e total pela `custos.calcular_resumo`. "Adicionar item" abre uma
  folha inferior (largura < 600 px) ou um diálogo. Remover pede confirmação. Modo local
  (Criar, Concluir: tudo vai numa chamada) ou gravado (Alterar: cada mudança chama
  `adicionar_item` / `editar_item` / `remover_item` e a tela recarrega com a versão nova).
- `ui/components/formulario_os.py`: Título, Descrição, Filial (só admin muda), Equipamento
  (lista da filial + "Outro" com campo obrigatório), Tempo previsto (`CampoDuracao`); para
  admin em OS concluída também Início/Fim (data + `CampoHora`) e Descrição do realizado.
- Telas: Criar (itens só na tela até "Salvar Ordem de Serviço"), Alterar (itens previstos
  só leitura quando `acoes.pode_editar_itens_previstos` é falso; admin em OS concluída
  edita os realizados), Concluir (itens previstos no topo, "Copiar itens previstos",
  prévia por categoria, total e tempo), Detalhe (Equipamento, Nº SAP, cartão Custos em
  tabela ou cartões pequenos no celular, com "Acima/Abaixo/Igual ao previsto", itens de
  cada fase recolhidos), Home (total previsto calculado).
- `ui/formularios.py`: `ItemLocal`, `ler_item` (usa os validadores puros do serviço),
  `para_entrada`, `copiar_itens`, `alteracoes_do_item`, `ler_equipamento`, `instante`,
  `previa_tempo`. Saíram `ler_valor`, `ler_tempo`, `valor_para_campo`, `tempo_para_campo`
  e `previa_diferencas` (o preço único não existe mais).
- `ui/historico.py`: frases dos eventos ITEM_ADICIONADO / ITEM_ALTERADO / ITEM_REMOVIDO e
  dos campos de equipamento; "Ordem de Serviço criada".

### Máscaras: comportamento medido (Chromium headless, Playwright)

Digitando '123456' e depois 3 backspaces, com o intervalo indicado entre as teclas:

| Ida e volta até o servidor | 0 ms | 40 ms | 80 ms | 150 ms | 300 ms |
|---|---|---|---|---|---|
| local (~0 ms) | ok / **12,32** | ok | ok | ok | ok |
| proxy 50 ms | ok / **12,32** | **12,46** / **0,01** | ok | ok | ok |
| proxy 150 ms | ok / **12,32** | **1,26** / **0,00** | **12,46** / **0,01** | **1.223,46** / **1,22** | ok |

(ok = 1.234,56 e depois 1,23.) Quando a pessoa digita mais rápido do que a ida e volta,
a reescrita do servidor chega atrasada e apaga teclas já digitadas. O proxy de teste
atrasa cada pacote TCP (a emulação de rede do Chrome não atrasa WebSocket). Não houve
teste em Android nem iOS reais; WebKit não está instalado aqui.

### Lacunas

- Decidir a alternativa para as máscaras (bloqueio acima).
- Quantidade usa teclado de texto: o teclado numérico do Flet (`KeyboardType.NUMBER`) vira
  `inputmode=numeric` no navegador, sem vírgula em alguns celulares.
- O layout de Custos (tabela ou cartões) é escolhido ao abrir o Detalhe; girar o celular
  só muda ao recarregar a tela.
- `flet.testing` existe mas precisa de numpy e do app de teste do Flutter: o teste de
  integração foi feito com Playwright no navegador, fora do pytest.

## Prompt 15 — proteção do login, IP do cliente, exposição na internet (18/11/2026)

### O que mudou

- **Atraso progressivo no lugar do bloqueio fixo** (`services/protecao_login.py`,
  `services/auth.py`): por login, 3 falhas livres e depois 2, 4, 8... s até 15 min;
  sucesso zera. Por IP, mais de 20 falhas em 15 min (contadas desde a última falha) põem
  o IP na mesma regra. Antes do instante permitido a tentativa é recusada com
  `ErroMuitasTentativas` (subclasse de `ErroAutenticacao`) sem conferir a senha.
  Logins inexistentes e inativos contam igual. O servidor não dorme: grava
  `proximo_permitido_em`.
- **Tabela `tentativas_login`** (migração `0006`): `chave` (HMAC-SHA256 hex com
  `OS_HMAC_SEGREDO`), `tipo` (LOGIN/IP), `falhas`, `proximo_permitido_em`,
  `atualizado_em`; único (tipo, chave). Linhas travadas com INSERT ... ON CONFLICT DO
  NOTHING + SELECT ... FOR UPDATE (login antes de IP, sempre). A mesma migração remove
  `usuarios.tentativas_falhas` e `usuarios.bloqueado_ate`; o downgrade as recria zeradas.
- `autenticar(login, senha, ip=None)`; a tela de login passa `page.client_ip` e mostra
  "Muitas tentativas. Aguarde alguns instantes e tente novamente." (única mudança de tela).
- Sem IP: chave fixa `desconhecido` e um aviso no log por tentativa.
- Logs de autenticação: só chaves HMAC (e o id do usuário no sucesso).
- `redefinir-senha` apaga o contador daquele login. CLI nova: `limpar-tentativas`
  (apaga contadores sem atividade há mais de 30 dias).
- `OS_HMAC_SEGREDO` obrigatória (mínimo 32 caracteres): sem ela o app não inicia.
- `docker/iniciar.sh`: `--forwarded-allow-ips "${OS_PROXIES_CONFIAVEIS:-127.0.0.1}"`
  (antes `'*'`) e `--no-access-log`.
- `docs/GO_LIVE.md` (checklist para a TI); `pip-audit` nas dependências de
  desenvolvimento (resultado: 69 pacotes, 0 vulnerabilidades conhecidas).

### Como o IP chega ao app

`uvicorn --proxy-headers` reescreve o cliente da conexão (inclusive do WebSocket) a
partir de `X-Forwarded-For` só quando a conexão vem de um endereço confiável; o flet-web
lê `websocket.client.host` e o entrega em `Page.client_ip`
(`flet_web/fastapi/flet_app.py`, flet 1.1.2). `Forwarded` (RFC 7239) não é lido pelo
uvicorn.

### Lacunas

- Endereço do proxy do Render não confirmado (ver GO_LIVE.md). Sem
  `OS_PROXIES_CONFIAVEIS` correta, todos os acessos aparecem com o IP do proxy e o limite
  por IP vale para todos juntos.
- A limpeza de `tentativas_login` precisa ser agendada fora do app.
- Contagem por login não expira com o tempo (só com sucesso, `redefinir-senha` ou a
  limpeza de 30 dias), como pedido.

## Decisões depois do prompt 15 (18/11/2026)

### IP do cliente (`osapp/rede.py`)

- O app resolve o IP num middleware ASGI em volta do app Flet; o uvicorn roda com
  `--no-proxy-headers`. Só com conexão direta vinda de `OS_PROXIES_CONFIAVEIS` (padrão
  `10.0.0.0/8`, loopback sempre): 1) `True-Client-Ip`; 2) `X-Forwarded-For` da direita
  para a esquerda, pulando confiáveis (a entrada mais à esquerda nunca vale por ser a
  primeira; lixo na cadeia interrompe a leitura); 3) o endereço direto. O valor escolhido
  precisa ser um IP válido. `X-Forwarded-Proto` de proxy confiável ajusta o esquema.
- `OS_DEPURAR_CABECALHOS_IP=1` (temporário, desligado por padrão) grava os cabeçalhos de
  encaminhamento e o IP escolhido. `*` em `OS_PROXIES_CONFIAVEIS` é recusado ao iniciar.

### Limite por IP e 4G (CGNAT)

- Por IP: `OS_LIMITE_FALHAS_IP` (padrão 100) falhas em 15 min, depois espera de 2, 4, 8...
  s até `OS_ATRASO_MAX_IP_SEGUNDOS` (padrão 60). Nunca bloqueia. Por login continua 3
  falhas livres e teto de 15 min (a proteção principal).

### Limpeza sem tarefa agendada

- Contador expirado (IP: 15 min sem falha; login: 30 dias sem atividade; nunca com espera
  pendente) é apagado antes de travar a chave numa nova tentativa, e numa varredura ao
  iniciar o app (`protecao_login.limpeza_ao_iniciar`; uma falha ali só gera aviso).
  `limpar-tentativas` fica para uso manual.

### Hospedagem

- Render só para teste com dados fictícios até a TI aprovar. `docker/iniciar.sh` recusa
  `OS_DATABASE_URL` em SQLite antes de migrar.

### Conferido

- Totais calculados: `test_custos.py` (`test_total_da_linha`, `test_resumo_por_categoria_e_total`,
  `test_detalhe_traz_itens_e_resumo`, `test_itens_nunca_tem_total_gravado`),
  `test_ordens_parte1.py::test_resumo_filtros_e_ordem` (total da Home),
  `test_relatorios.py`, `test_ui_formularios.py::test_resumo_previa_usa_o_calculo_do_servico`.
- Numeração concorrente: `test_numeracao.py::test_vinte_criacoes_simultaneas` (20
  threads; roda no PostgreSQL, pulado no SQLite).

## Prompt 16 — modelo de dados: papéis, solicitações, instantes de status (19/11/2026)

**Só modelo de dados: as regras vêm no prompt 17. Pode ser implantado sozinho.**

- `usuarios.papel` ('usuario' | 'manutencao' | 'admin', padrão no banco 'manutencao',
  CHECK). Dados: is_admin -> 'admin', demais -> 'manutencao'. `is_admin` continua e fica
  coerente: `criar_usuario`, `definir_perfil` e `definir_papel` gravam os dois juntos.
- `tipos_manutencao` (CORRETIVA, PREVENTIVA, PREDITIVA, MELHORIA, OUTRO), tabela.
- `ordens_servico`: `origem` (padrão 'manutencao'), `urgencia`, `prioridade`, `tipo_id`,
  `nota_conclusao`, `aberta_em` (padrão no banco: agora), `inicio_execucao_em`,
  `concluida_em`, `cancelada_em`, `cancelada_por_id`. Dados: aberta_em = criado_em,
  inicio_execucao_em = iniciado_em, concluida_em = concluido_em. `iniciado_em` e
  `concluido_em` continuam (o código atual ainda os grava). `tempo_previsto_minutos` aceita
  NULL. CHECKs de valores e de linha do tempo; índices (filial_id, origem, aberta_em) e
  (status).
- Migração `0007`: antes dos CHECKs procura OS que os violariam e para com a lista dos
  números. Downgrade: OS sem tempo previsto recebem 1 minuto (aviso no log).
- CLI: `previa-papeis` (lê só login, is_admin e filial; roda antes ou depois da migração;
  não altera nada) e `definir-papel LOGIN PAPEL`.

### Lacunas

- `valor_previsto_centavos` não existe desde o prompt 13 (itens de custo): só
  `tempo_previsto_minutos` passou a aceitar NULL.
- O perfil gerente (`is_gerente`) continua separado do papel.

## Prompt 17 — papéis e fluxo de solicitação nos serviços (19/11/2026)

**As telas atuais não funcionam com estes serviços: implantar só junto com o prompt 19.**

### Funções

- `Ator.papel` ('usuario' | 'manutencao' | 'admin'); `is_admin`, `is_manutencao` e
  `is_usuario` são propriedades derivadas. A coluna `usuarios.is_admin` saiu (migração
  `0008`); `Usuario.is_admin` ficou como propriedade só de leitura.
- `criar_solicitacao(ator_id, titulo, descricao, urgencia, filial_id=None)`.
- `criar_os(ator_id, titulo, descricao, itens_previstos=None, tempo_previsto_minutos=None,
  filial_id=None, *, equipamento_id, equipamento_outro, tipo_id, prioridade)`: só
  manutenção e admin; previsto opcional.
- `obter_os` e `listar_os` devolvem `OsVisaoSolicitante` / `ResumoSolicitante` para usuario
  (consulta só com as colunas permitidas) e `OsDetalhe` / `OsResumo` para os demais.
  `listar_os` aceita `origem`. `listar_eventos` e `listar_tipos`: ErroPermissao para usuario.
- `editar_solicitacao` (título, descrição, urgência), `editar_os` (tempo previsto, tipo,
  prioridade, equipamento; título e descrição só em OS de origem manutenção; filial só
  admin; realizado só admin em concluída).
- `iniciar_execucao` (exige `previsto_completo`), `desfazer_inicio` (apaga executor e
  `inicio_execucao_em`), `concluir_os(..., nota_conclusao)` (5 a 500 caracteres),
  `cancelar(ator_id, os_id, versao)`.
- `previsto_completo(ordem)` / `pendencias_para_iniciar(ordem)`: tempo previsto, pelo menos
  um item de custo previsto, tipo, prioridade e equipamento. `OsDetalhe` traz as pendências.
- Itens previstos: quem pode `editar_os`; numa OS ABERTA o último item previsto pode sair.
- CLI: `criar-usuario --papel`, `definir-papel`, `reclassificar-origem NUMERO
  solicitacao|manutencao --responsavel LOGIN [--aplicar]`.

### Migração `0008`

Copia de novo `criado_em`, `iniciado_em` e `concluido_em` para `aberta_em`,
`inicio_execucao_em` e `concluida_em` (OS gravadas pelo código antigo depois da 0007) e
`is_admin` para `papel`; depois remove `usuarios.is_admin`, `ordens_servico.iniciado_em` e
`ordens_servico.concluido_em`. O downgrade os recria a partir de `papel` e dos instantes.

### Testes

`tests/test_papeis_fluxo.py`: matriz papel x ação x status com 168 células (7 atores x 6
ações x 4 status), cada uma conferindo também a flag de `acoes`; campos devolvidos ao
usuario (nomes de todos os objetos); SQL executado para o usuario sem colunas restritas;
visibilidade por filial; previsto incompleto; nota; cancelamento; desfazer; instantes com
relógio substituído; migração 0008 com dados.

### Lacunas

- `previa-papeis` depois da 0008 lista o papel atual; a prévia antes da 0007 se faz com o
  código do prompt 16 (commit 3c66de8).

## Prompt 19 — telas por papel: solicitação, assumir, cancelar, nota de conclusão (19/11/2026)

**Implantar junto com o prompt 17.**

- `ui/rotulos.py` (puro): rótulos de status (com Cancelada), urgência/prioridade, origem e
  papel; `ordenar_solicitacoes_abertas` (Emergencial primeiro, depois a mais antiga).
  Selos com a palavra sempre visível (`basicos.selo_nivel`, `selo_origem`); Emergencial em
  vermelho cheio com ícone. Cores novas em `theme.py`.
- `ui/navegacao.py` (puro): `destinos(papel)` — usuario: Ordens e Nova Solicitação;
  manutencao: Ordens e Nova Ordem de Serviço; admin: as três. `ve_relatorios(papel)`: o
  menu só mostra Relatórios para manutenção e administrador.
- Telas novas: Nova Solicitação (`/solicitacao/nova`; urgência em quatro opções de 56 px;
  filial travada; mostra o número gerado), Editar solicitação (`/os/{id}/solicitacao`),
  Assumir solicitação (`/os/{id}/assumir`: a solicitação só leitura no topo; tipo,
  prioridade e previsto; "Salvar" e "Salvar e iniciar execução", que mostra o que falta
  com o texto do serviço).
- Home: o usuario vê número, título, urgência, status, solicitante e data; manutenção e
  administrador veem também origem e prioridade e o filtro rápido "Solicitações abertas".
- Detalhe: usuario só com o modelo reduzido (linha do tempo e, se concluída, a "Nota da
  manutenção" em destaque; Editar e Cancelar solicitação conforme `acoes`); manutenção e
  administrador com urgência e prioridade separadas, tipo, as quatro datas, a nota e o
  botão Cancelar (com confirmação "Sim, cancelar").
- Formulário de OS: tipo e prioridade; previsto e equipamento opcionais; título e
  descrição de uma solicitação só leitura. Concluir: "Nota para o solicitante" (500
  caracteres, contador, ajuda "O solicitante verá esta nota.").
- Rotas digitadas por usuario (`/os/{id}/editar`, `/assumir`, `/concluir`, `/os/nova`):
  `listar_tipos` recusa e a tela mostra a mensagem genérica.
- Seed com exemplos: `usuario.teste` (papel usuario, 1007).
- Conferido no navegador (Playwright, 390 px e 1280 px) os 7 passos do VERIFY.

## Prompt 18 — relatório v1: tempo de resposta e até a solução (19/11/2026)

- `services/relatorios.py`: `relatorio_tempos(ator_id, data_inicio=None, data_fim=None,
  status=None, filial_id=None)` -> `RelatorioTempos` (resposta, solução, por urgência,
  backlog). Só solicitações, nunca canceladas; período por `aberta_em` em dias de OS_TZ
  (padrão: últimos 30 dias); status entre Aberta, Em execução, Concluída. Manutenção só a
  própria filial; administrador uma ou todas; usuario: ErroPermissao. A consulta lê só id,
  urgência e os três instantes; média e mediana em segundos inteiros no Python
  (`medir`), meio para cima. Backlog (ABERTA agora) ignora período e status.
- `formatacao.formatar_tempo(segundos)`: '45 min', '3 h 20 min', '2 d 4 h'.
- Tela `/relatorios` "Relatório de tempos de atendimento" (filtros de período, status e,
  para admin, filial; cartões de resposta e solução com média, mediana e n; por urgência
  em tabela ou cartões no celular; "Solicitações em aberto"; nota sobre média e mediana;
  "Sem dados no período."). Destino de primeiro nível "Relatórios" para manutenção e
  administrador, entrada no menu e cartão na Home. O relatório mensal anterior foi para
  `/relatorios/mensal`, com botão a partir do novo.
- Conferido no navegador: com 5 solicitações (uma cancelada) os números batem com a
  conta à mão; usuario.teste não tem Relatórios e `/relatorios` mostra a recusa genérica.

## Prompt 20 — gestão de usuários e troca de senha (19/11/2026)

- Migração `0009`: `usuarios.deve_trocar_senha` (padrão falso), `usuarios.versao` (trava
  otimista, como nas OS) e a tabela `usuarios_eventos` (admin_id, usuario_id, data_hora,
  campo, valor_antigo, valor_novo), só de inserção. Downgrade remove as três.
- `services/usuarios.py` (só administrador, todas as filiais): `listar_usuarios` (busca
  por nome ou login; filtros papel, filial, ativo), `obter_usuario`,
  `listar_eventos_usuario`, `criar_usuario` (senha temporária), `alterar_usuario` (nome,
  filial, papel, ativo; com versão), `redefinir_senha` (temporária) e, para todos,
  `trocar_propria_senha` (confere a atual). Senha: pelo menos 10 caracteres e diferente
  do login (`senhas.SENHA_MIN = 10`, vale também para CLI e seed). O último administrador
  ativo não perde o papel nem se desativa. Um evento por campo; senha só como
  'senha redefinida' / 'senha alterada'.
- CLI pelos mesmos serviços (eventos com admin_id nulo): `criar-usuario` e
  `redefinir-senha` criam senha temporária; `desativar-usuario`, `definir-papel` e
  `definir-perfil` respeitam a regra do último administrador. O seed não marca troca.
- Telas: Configurações com "Alterar senha" (todos) e "Usuários" (admin); `/usuarios`
  (busca, filtros, novo), `/usuarios/novo` e `/usuarios/{id}` (alterar, Redefinir senha,
  Desativar/Reativar com confirmação, histórico); `/trocar-senha` obrigatória: a guarda
  de rotas (`sessao.decidir_rota`) manda para lá enquanto a troca estiver pendente.
- Conferido no navegador: o administrador cria um usuário; no login dele a troca é
  obrigatória (recarregar e digitar outra rota não pula); senha igual ao login recusada;
  depois da troca, a Home.

### Lacunas

- A troca obrigatória é aplicada pela guarda de rotas da interface; os serviços não
  recusam outras chamadas de quem ainda tem senha temporária.

## Prompt 21 — sem cadastro de equipamento; texto de busca normalizado (21/11/2026)

- Decisão de 21/11: o que foi atendido é descrito pelos itens de custo. Saíram o modelo, o
  repositório e o serviço do cadastro, os campos da OS, a pendência no
  `previsto_completo` (agora: tempo, itens previstos, tipo e prioridade), os comandos de
  CLI, o seed de exemplo, a lista suspensa nas telas e os testes que só tratavam disso.
  `numero_sap` fica.
- `osapp/busca.py`: `normalizar_busca(texto)` (NFKD sem marcas combinantes, casefold,
  espaços únicos, aparado; None/'' -> ''), sem Flet nem banco. O termo digitado deve
  passar pela mesma função (a busca em si muda no prompt 22).
- `ordens_servico.busca_texto` (título + descrição) e `os_itens_custo.busca_texto`
  (descrição): texto, padrão ''. Mantidos por eventos `before_insert`/`before_update` do
  ORM nos dois modelos. Inserção/alteração em lote pulam esses eventos: há um teste que
  falha se aparecerem em `src/`.
- Migração `0010`: cria e preenche as duas colunas (cópia congelada da normalização no
  próprio arquivo), remove a chave estrangeira, as duas colunas da OS e a tabela do
  cadastro. O downgrade recria a estrutura vazia (os dados não voltam; fonte: o CSV).
- CLI: `recalcular-busca` (idempotente; imprime quantas linhas mudaram) e a exportação
  prévia `exportar-equipamentos ARQUIVO.csv`, em `osapp/exportacao_legada.py`, que
  lê as tabelas por reflexão: os modelos do app não têm mais essas colunas. É o único
  arquivo de `src/` com o nome antigo (exceção no teste de referências).

### Quando um índice pg_trgm passa a valer a pena

A busca atual é `LIKE '%termo%'` sobre `busca_texto`, sem índice: varre a tabela (das OS
da filial, quando filtrada) e funciona igual no SQLite e no PostgreSQL. Com algumas
dezenas de milhares de OS ou itens por filial, ou quando uma busca passar de ~300 ms
medida no banco de produção (`EXPLAIN ANALYZE`), vale criar no PostgreSQL
`CREATE EXTENSION pg_trgm` e índices GIN `gin_trgm_ops` em `ordens_servico.busca_texto`
e `os_itens_custo.busca_texto`, numa migração só para PostgreSQL (o SQLite continua
varrendo). Antes disso o índice só custa espaço e tempo de gravação.

## Prompt 22 — escopo da busca, sugestões de descrição, relatório com busca (21/11/2026)

- Uma só função monta a busca: `ordens.condicao_busca(termo, escopo, ator)`. O termo
  passa por `normalizar_busca` e vira palavras; cada palavra precisa aparecer no escopo
  da mesma OS (`LIKE` com `autoescape`: `%` e `_` valem como caracteres comuns).
  Escopos (`ordens.ESCOPOS`): `itens` (padrão; `busca_texto` dos itens das duas fases)
  e `tudo` (título + descrição + itens). O papel usuario busca sempre só em título +
  descrição, qualquer que seja o escopo pedido. Itens entram por `EXISTS` em
  `os_itens_custo` (nunca JOIN): a OS aparece e conta uma vez. Termo só com dígitos e
  traços também casa com `numero`, em qualquer escopo. A filial entra na mesma consulta.
- `listar_os(..., escopo='itens')`; o repositório recebe a condição pronta
  (`_filtrar(..., condicao, ...)`) em vez do texto.
- `custos.sugerir_descricoes(ator_id, filial_id, termo, limite=8)`: manutenção da
  própria filial e administrador (usuario: `ErroPermissao`); termo normalizado com menos
  de 2 caracteres devolve []; agrupa por `busca_texto` do item, mais usado primeiro e
  depois o uso mais recente (`criado_em`), e devolve a grafia original mais frequente
  de cada grupo; no máximo 20.
- `relatorios.relatorio_tempos(..., termo=None, escopo='itens', pagina=1)`: o termo
  restringe o relatório inteiro (tempos, por urgência e também as solicitações em
  aberto). Com termo, `busca` (`ResultadoBusca`) traz correspondentes / total do
  período / percentual (`custos.percentual`, None com total 0), custos via
  `calcular_resumo` (previsto de todas; previsto x realizado e diferença só das
  concluídas) e a lista paginada (50, mais recentes primeiro). Sem termo, nada muda.
  Os tempos usam a mesma função `_medidas` com ou sem busca.
- Telas: seletor `Itens`/`Tudo` (`ui/components/escopo_busca.py`, chips) na Home e no
  relatório, só para manutenção e administrador; para usuario a dica do campo diz que a
  busca olha título e descrição. Editor de itens: sugestões numa lista sob o campo
  Descrição (após 2 caracteres e ~300 ms; opções de 48 px), porque o `ft.AutoComplete`
  do Flet 1.1.2 tem o próprio campo de texto e não aceita o campo padrão do app. No
  relatório: linha de resumo, cartões de tempo, cartão de custos e lista (toque abre o
  Detalhe); sem correspondência: 'Nenhuma ordem corresponde à busca no período.'
- Sem mudança em modelos nem migrações.
