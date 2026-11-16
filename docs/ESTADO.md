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
