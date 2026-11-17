# Auditoria de segurança — prompt 9

Verificação de todo o código contra a lista do prompt 9. Método: leitura do código, buscas
com `grep`, uma checagem por AST das funções públicas de `services/ordens.py` e os testes
automatizados. Os números de linha valem para o commit do prompt 9.

## Resumo

| Item | Assunto | Resultado |
|---|---|---|
| a | Senhas | Passa |
| b | `carregar_ator` e regras de filial/papel em `ordens.py` | Passa |
| c | Sem SQL cru | Passa (uma instrução `PRAGMA` constante, exigida) |
| d | Validação de entradas nos serviços | Passa (pendência das colunas de valor corrigida depois, ver item d) |
| e | Guarda de rotas, logout e tempo limite | Passa |
| f | Segredos no repositório | Passa |
| g | Mensagens ao usuário | Passa |
| h | Dados fictícios | Passa |
| i | Histórico somente de inserção | Passa |

Nenhuma falha dentro da interface. A pendência fora da interface encontrada no item d (tipo
das colunas de valor no PostgreSQL) foi corrigida depois, na migração `0002`.

## a. Senhas — Passa

- Só argon2id: `services/senhas.py` usa `argon2.PasswordHasher()` com os padrões da
  biblioteca. Busca por `hashlib`, `bcrypt`, `md5`, `sha1` em `src/`: nenhuma ocorrência.
  Teste: `test_auth.py::test_hash_e_argon2id_e_nao_contem_a_senha`.
- Logs: `services/auth.py` registra apenas `usuario_id` e o motivo (linhas 54 a 102); login
  inexistente é registrado sem o texto digitado (linha 69). A única mensagem de log com a
  palavra "senha" é `"Senha redefinida: usuario_id=%s."` (`administracao.py:127`), sem valor.
  Teste: `test_auth.py::test_logs_nao_contem_senha_hash_nem_login_digitado`.
- `print`: só em `cli.py` e `seed.py`, com mensagens fixas ou `ErroValidacao.mensagem`.
  Testes: `test_seed_exige_senha_e_nao_a_imprime`, `test_cli`.
- Exceções: `ErroAutenticacao` não tem argumentos (`erros.py`). A CLI lê senhas com
  `getpass` e não aceita `--senha` (`test_cli_nao_aceita_senha_por_argumento`).
- Estado de sessão: `ui/sessao.py::SessaoUI` não tem campo de senha, hash ou token
  (`test_ui_rotas_sessao.py::test_sessao_nao_guarda_senha_nem_hash`). A tela de login limpa
  o campo de senha depois de toda tentativa (`ui/views/login.py:81`).
- `Config.__repr__` oculta a URL do banco (`config.py:29`, `test_repr_nao_expoe_a_url`).

## b. `carregar_ator` e regras em `services/ordens.py` — Passa

Checagem por AST: a primeira instrução de cada função pública que recebe `ator_id` é
`ator = carregar_ator(ator_id)`: `criar_os` (351), `obter_os` (395), `listar_os` (407),
`listar_eventos` (450), `listar_filiais` (468), `editar_os` (519), `iniciar_execucao` (595),
`desfazer_inicio` (618), `concluir_os` (648). Observação: `registrar_evento` (311) também é
público, mas é o auxiliar de gravação do histórico exigido pelo prompt 4; recebe uma
`Session` e não um ator, e a interface não tem como obter uma sessão de banco
(`test_ui_nao_importa_modelos_nem_repositorios`).

| Regra | Onde | Teste que prova |
|---|---|---|
| Usuário inativo ou inexistente é recusado em toda função | `auth.carregar_ator` | `test_ordens_parte1::test_usuario_inativo_e_recusado_em_toda_funcao`; matriz (coluna `inativa`) |
| Não admin só cria na própria filial | `criar_os` (355) | `test_usuario_comum_nao_cria_em_outra_filial` |
| Admin cria em qualquer filial existente | `criar_os` | `test_admin_cria_em_qualquer_filial` |
| OS de outra filial = OS inexistente | `_carregar_visivel` (253) | `test_usuario_comum_nao_le_os_de_outra_filial` |
| Lista de não admin restrita à filial | `listar_os` (415) | `test_lista_de_usuario_comum_nunca_tem_outra_filial`, `test_usuario_comum_nao_lista_outra_filial` |
| Admin lê e lista tudo | `listar_os`, `obter_os` | `test_admin_le_qualquer_os_e_lista_todas` |
| `listar_filiais`: admin todas, demais a própria | `listar_filiais` | `test_listar_filiais` |
| Quem edita, inicia, desfaz e conclui, em cada status | `_pode_editar` (214), `_pode_transicionar` (224) | `test_ordens_parte2::test_matriz_de_permissoes` (72 células) |
| Transição fora da tabela é recusada | `_mudar_status` (507), `concluir_os` (653) | `test_transicao_fora_da_tabela_e_recusada_ate_para_admin` |
| Só o executor (ou admin) conclui e desfaz | `status.TRANSICOES` | `test_quem_iniciou_e_o_unico_usuario_comum_que_conclui_ou_desfaz` |
| Realizado não é gravado por edição antes da conclusão | `editar_os` (533) | `test_realizado_nao_e_gravado_por_edicao_antes_da_conclusao` |
| Depois de concluída só admin edita | `_pode_editar` | `test_depois_de_concluida_so_admin_edita_inclusive_o_realizado` |
| Só admin muda a filial | `editar_os` (533) | `test_so_admin_muda_a_filial` |
| Campo desconhecido ou proibido | `editar_os` (533) | `test_campo_desconhecido_ou_proibido` |
| `acoes` concorda com as funções | `_acoes` | `test_matriz_de_permissoes`, `test_acoes_por_ator_em_cada_status` |

## c. Sem SQL cru — Passa

- Busca por `text(`, `.execute(`, `exec_driver_sql`, `raw_connection` em `src/` e
  `migrations/`: uma ocorrência, `db.py:40`, `cursor.execute("PRAGMA foreign_keys=ON")`.
  É uma string constante, sem dado de usuário, exigida pelo prompt 2 (chaves estrangeiras
  no SQLite).
- Busca por f-strings, `%` ou concatenação perto de `select/insert/update/delete/where`
  em `src/` (fora de `ui/`): nenhuma ocorrência.
- A busca textual usa `icontains(..., autoescape=True)` (`ordem_servico_repo.py`), com
  parâmetros vinculados. Testes: `test_repositorios::test_busca_trata_curingas_como_texto`,
  `test_ordens_parte1::test_busca_trata_caracteres_especiais_como_texto`.

## d. Validação de entradas nos serviços — Passa, com uma pendência

- Tipos, tamanhos e faixas: `_validar_titulo` (148), `_validar_texto_longo` (159),
  `_validar_valor` (168), `_validar_tempo` (178), `_validar_instante` (192),
  `_validar_periodo` (202). Testes: `test_validacao_recusa` (22 casos),
  `test_validacao_aceita_os_limites`, `test_concluir_recusa_campo_ausente_ou_invalido`
  (17 casos), `test_concluir_limites_de_tempo`, `test_editar_usa_a_mesma_validacao_de_criar`,
  `test_admin_corrigindo_realizado_passa_pela_validacao`, `test_listar_valida_os_filtros`.
- Transições: tabela única em `services/status.py`; ver item b.
- Versão (trava otimista): `_conferir_versao` (478) e `version_id_col` do modelo. Testes:
  `test_versao_desatualizada_gera_conflito_e_nao_muda_nada`, `test_duas_edicoes_com_a_mesma_versao`.
- Autenticação: `test_entrada_longa_ou_invalida_e_recusada_antes_de_qualquer_hash`.
- A leitura local na interface (`ui/formularios.py`) é conveniência; os valores passam de
  novo pela validação do serviço.

**Pendência fora da interface (corrigida depois do prompt 9, migração `0002`):** as duas
colunas passaram a `BigInteger` e a suíte inteira passa em PostgreSQL 16. Texto original
do achado: `valor_previsto_centavos` e
`valor_realizado_centavos` são colunas `Integer` (`models/ordem_servico.py`, migração
`0001`). No PostgreSQL isso é um inteiro de 32 bits (máximo 2.147.483.647 centavos, cerca de
R$ 21,4 milhões), abaixo do limite aceito pelo serviço (9.999.999.999 centavos). No SQLite
funciona. Efeito no PostgreSQL: um valor acima de R$ 21,4 milhões passaria na validação e
falharia no banco; o usuário veria a mensagem genérica e nada seria gravado (não há
corrupção nem exposição de dados). Correção sugerida antes de usar PostgreSQL: trocar as
duas colunas para `BigInteger` no modelo e em uma migração. Não foi feita porque os prompts
proíbem alterar modelos e migração sem relatar antes.

## e. Guarda de rotas, logout e tempo limite — Passa

- Toda tela é montada em `App._mostrar`, chamado só por `App._navegar` depois de
  `sessao.aplicar_navegacao` (`ui/app.py:197`); `page.views` só é escrito em `App._montar`
  (247, 248). Não há `page.add` em nenhuma tela.
- Testes de `decidir_rota`: `test_sem_login_toda_rota_vai_para_login`,
  `test_com_login_em_login_vai_para_a_home`, `test_sessao_expirada_vai_para_login`,
  `test_link_direto_e_lembrado_ate_o_login`, `test_aritmetica_do_tempo_limite`,
  `test_expiracao_encerra_a_sessao_e_deixa_a_mensagem`.
- Verificado no navegador (Chromium headless): URL `/os/1` sem login mostra o login; "Sair"
  volta ao login e o botão voltar do navegador continua no login; com
  `OS_SESSAO_TIMEOUT_MIN=1`, depois de 62 s parado a navegação seguinte mostrou o login com
  "Sessão expirada. Entre novamente.".
- `App.chamar` confere a sessão antes de toda chamada de serviço e cada serviço recarrega
  o ator: um usuário desativado é barrado na ação seguinte.
- Limite conhecido: a tela aberta continua visível até a próxima navegação ou ação (o
  prompt 6 pede a verificação nesse momento, não um temporizador).

## f. Segredos no repositório — Passa

- `.env` e `*.db` estão no `.gitignore`; `git ls-files` não lista nenhum dos dois.
- `.env.example` tem só valores de exemplo (`sqlite:///./dev.db`), sem senha.
- Não há URL de banco padrão no código (`config.py`); `alembic.ini` não tem
  `sqlalchemy.url` (`test_migracao::test_alembic_ini_nao_contem_url`).
- Busca por URLs com credenciais em todo o repositório: uma ocorrência,
  `tests/test_config.py:65`, a URL fictícia `postgresql://u:segredo@h/db`, usada para testar
  que `repr(Config)` não mostra a senha. Não é um segredo real.
- As senhas dos testes (`senha-ficticia-123`) são fictícias; a do seed vem de `OS_SEED_SENHA`.

## g. Mensagens ao usuário — Passa

- `App.chamar` (`ui/app.py:379` a 397): `ErroValidacao` mostra `exc.mensagem`;
  `ErroAutenticacao` leva ao login; qualquer outra exceção mostra a mensagem genérica e vai
  para o log com traceback (`logger.exception`, 395).
- Erros tratados pelas telas mostram textos fixos: "Usuário ou senha inválidos.", "OS não
  encontrada.", "Esta OS foi alterada por outra pessoa. Atualize e tente novamente." e a
  genérica.
- `str(exc)` na interface aparece em `formulario_os.py` (163, 206) e `concluir.py` (183,
  208), sempre para `ValueError` levantado por `ui/formularios.py`, cujas mensagens são as
  constantes `MSG_*` em português (`test_ui_formularios.py`).
- `main.py:33` imprime `ConfigError` no terminal do servidor, não para o usuário.

## h. Dados fictícios — Passa

- Seed: "Filial Modelo Norte", "Filial Modelo Sul", "Administrador Fictício", "Marina Teste",
  "João Fictício", "Carlos Exemplo" (`seed.py`).
- Busca por nomes de empresas do setor e por arquivos de imagem em `src/`, `tests/`, `docs/`,
  `README.md` e `migrations/`: nenhuma ocorrência. O logo é um ícone do Material mais o texto
  "OS" (`ui/components/cabecalho.py::logo`). Não há diretório de assets.
- Observação: o nome do repositório no GitHub não faz parte do código e não aparece na
  interface.

## i. Histórico somente de inserção — Passa

- `OsEventoRepo` só tem `adicionar` e `listar_por_os`
  (`test_repositorios::test_os_evento_repo_e_somente_insercao`). Não há `delete` em `src/`.
- `OsEvento(` só é instanciado em `registrar_evento` (`ordens.py:322`).
- Criação, edição e mudança de status gravam o evento na mesma transação. Testes:
  `test_usuario_comum_cria_os_na_propria_filial`, `test_editar_dois_campos_grava_dois_eventos`,
  `test_edicao_sem_mudanca_nao_grava_evento_nem_muda_versao`,
  `test_iniciar_define_executor_e_evento`, `test_concluir_preenche_realizado_e_eventos`,
  `test_se_o_evento_falha_a_os_nao_e_criada`, `test_se_o_evento_falha_a_alteracao_e_desfeita`.
- Limite conhecido: a proteção é da aplicação. Quem tiver acesso direto ao banco pode
  alterar a tabela; para impedir isso seria preciso restringir permissões no PostgreSQL.

## Outros pontos observados (fora da lista)

- O bloqueio de login é por usuário (5 falhas, 15 minutos). Não há limite por endereço IP.
- O app precisa ficar atrás de um proxy com HTTPS (ver README); ele próprio fala HTTP.
- PostgreSQL: a suíte inteira (527 testes) passa em PostgreSQL 16 com o driver psycopg 3.

## Adendo — relatórios e perfil gerente (17/11/2026)

- **Relatórios (`services/relatorios.py`):** `gerar_relatorio` começa por `carregar_ator`;
  usuário comum e gerente só consultam a própria filial (`ErroPermissao` para outra, com
  log); o relatório completo só é preenchido quando `permissoes.pode_ver_relatorio_completo`
  permite (gerente na própria filial, administrador). Testes: `tests/test_relatorios.py`
  (`test_operario_ve_so_o_basico_da_propria_filial`,
  `test_gerente_ve_o_completo_da_propria_filial_e_nada_de_outra`, `test_admin_ve_tudo`,
  `test_relatorio_basico_nao_tem_dado_sensivel`, `test_desativar_gerente_tira_o_acesso_na_hora`).
- **Consultas novas:** `OrdemServicoRepo.contar_por_status`, `contar_criadas` e
  `listar_concluidas` usam `select()` do SQLAlchemy com parâmetros vinculados; o
  `self._s.execute(...)` recebe um objeto de consulta, não texto.
- **Execução de migrações (`migrations/env.py`):** no SQLite, `PRAGMA foreign_keys=OFF/ON` e
  `PRAGMA foreign_key_check` (textos constantes, sem dado de usuário) cercam a migração; ao
  fim, qualquer referência inválida interrompe com erro. Correção de um defeito real: com as
  chaves estrangeiras ligadas, migrações que recriam tabelas falhavam no SQLite assim que havia
  dados. Teste: `test_migracao.py::test_migracoes_com_dados_existentes` (falha sem a correção).
  No PostgreSQL (produção) nada muda.
- **Inicialização simultânea (17/11/2026):** migração e seed rodam sob uma trava consultiva
  do PostgreSQL (`db.trava_de_inicializacao`, via `select(func.pg_advisory_lock(...))`, sem
  SQL em texto). Antes, com três instâncias subindo juntas, duas falhavam por chave
  duplicada. Teste: `test_migracao.py::test_instancias_simultaneas_migram_e_semeiam_uma_de_cada_vez`
  (roda com `OS_TEST_DATABASE_URL` em PostgreSQL; falha sem a trava).
