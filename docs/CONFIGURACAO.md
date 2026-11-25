# Configuração (variáveis de ambiente)

Toda a configuração do app vem de variáveis de ambiente, lidas **somente** em
`src/osapp/config.py` (há teste que garante isso). Em desenvolvimento, um arquivo `.env`
na pasta do projeto é lido uma vez; ele nunca sobrescreve uma variável já definida no
ambiente. O modelo com todos os nomes está em `.env.example` (valores de exemplo, nunca
reais).

Nada no código depende de um provedor de hospedagem ou de banco: valores próprios de um
provedor (URL do banco, cabeçalho de IP do proxy, endereços do proxy) ficam só nas
configurações da hospedagem.

Se uma variável obrigatória faltar ou um valor for inválido, o app não sobe e diz qual
variável corrigir.

## Essenciais

| Variável | Obrigatória | Padrão | Significado |
|---|---|---|---|
| `OS_DATABASE_URL` | **sim** | — (não há padrão) | URL padrão do SQLAlchemy. Produção: PostgreSQL, `postgresql://usuario:senha@host:5432/banco` (o app troca para o driver psycopg). Aceita `?sslmode=require` e outros parâmetros do libpq. Contém senha: segredo. |
| `OS_HMAC_SEGREDO` | **sim** | — | Segredo do HMAC (tentativas de login, código de confirmação de e-mail). Mínimo de 32 caracteres aleatórios, diferente em cada ambiente. Segredo. |
| `OS_TZ` | não | `America/Sao_Paulo` | Fuso (IANA) de exibição e digitação de datas. |
| `OS_SESSAO_TIMEOUT_MIN` | não | `30` | Minutos sem atividade até encerrar a sessão. |
| `OS_LOG_LEVEL` | não | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` ou `CRITICAL`. |

## Conexão com o banco

| Variável | Obrigatória | Padrão | Significado |
|---|---|---|---|
| `OS_DB_RECICLAR_CONEXAO_SEGUNDOS` | não | `300` | Conexões do pool mais velhas que isto são renovadas (servidores e proxies de banco encerram conexões paradas). |
| `OS_DB_TIMEOUT_CONEXAO_SEGUNDOS` | não | `10` | Tempo máximo para abrir uma conexão com o PostgreSQL. |

## Login e IP do cliente

| Variável | Obrigatória | Padrão | Significado |
|---|---|---|---|
| `OS_LIMITE_FALHAS_IP` | não | `100` | Falhas de login de um mesmo IP em 15 min antes da espera por IP. |
| `OS_ATRASO_MAX_IP_SEGUNDOS` | não | `60` | Teto da espera por IP. |
| `OS_PROXIES_CONFIAVEIS` | não | `10.0.0.0/8` | IPs ou redes (vírgula) do proxy reverso. Só de conexões vindas daí os cabeçalhos de encaminhamento são aceitos. Loopback sempre incluído. `*` é recusado. Atrás de um nginx na mesma máquina: `127.0.0.1`. |
| `OS_CABECALHO_IP_CLIENTE` | não | vazio | Nome de um cabeçalho que o proxy confiável preenche com o IP do cliente (por exemplo `True-Client-Ip`). Só use se o proxy **sobrescreve** esse cabeçalho; senão o cliente poderia escrevê-lo. Vazio: usa só o `X-Forwarded-For`, lido da direita para a esquerda. |
| `OS_DEPURAR_CABECALHOS_IP` | não | `0` | `1` grava no log os cabeçalhos de encaminhamento e IPs crus. Temporário, para conferir o proxy. |

## Seed (primeira subida)

| Variável | Obrigatória | Padrão | Significado |
|---|---|---|---|
| `OS_SEED_SENHA` | só na primeira subida | — | Senha inicial do `admin` criado pelo seed (mínimo 10 caracteres). Remover depois. Segredo. |
| `OS_SEED_EXEMPLOS` | não | `0` | `1` cria usuários fictícios de exemplo. **Nunca em produção.** |

## E-mail (prompt 32) e alertas (prompt 33)

| Variável | Obrigatória | Padrão | Significado |
|---|---|---|---|
| `OS_SMTP_HOST` | só para e-mail | — | Servidor SMTP da conta remetente. Sem as variáveis de SMTP os e-mails ficam pendentes na fila. |
| `OS_SMTP_PORTA` | só para e-mail | — | `587` (STARTTLS) ou `465` (SSL). |
| `OS_SMTP_TLS` | só para e-mail | — | `starttls` ou `ssl` (`nenhum` só com host `localhost`, para testes locais). |
| `OS_SMTP_USUARIO` | não | — | Usuário da conta remetente (vai junto com a senha). |
| `OS_SMTP_SENHA` | não | — | Senha da conta remetente. Segredo. |
| `OS_SMTP_REMETENTE` | só para e-mail | — | Endereço do remetente (From). |
| `OS_BASE_URL` | não | — | Endereço público do app, para o link dos e-mails (ex.: `https://os.empresa.com.br`). |
| `OS_EMAIL_MAX_TENTATIVAS` | não | `6` | Tentativas de envio antes de a mensagem ficar como 'falhou'. |
| `OS_EMAIL_HABILITADO` | não | `0` | Prompt 46. `1` liga o e-mail. Com `0` (padrão) o trabalhador da fila não sobe e nada entra em `email_fila` (avisos de solicitação, códigos de confirmação, alertas de erro grave); os erros graves ficam só no log. |
| `OS_ALERTAS_EMAIL` | não | `1` | `0` desliga o e-mail dos alertas de erro grave (ficam só no log). Só vale com `OS_EMAIL_HABILITADO=1`. |

## Guia rápido (prompt 39)

| Variável | Obrigatória | Padrão | Significado |
|---|---|---|---|
| `OS_GUIA_ARQUIVO` | não | `docs/guia/guia.yaml` | Arquivo do guia do botão '?'. Editado no servidor, vale sem reiniciar (docs/guia/COMO_EDITAR.md). |

## Ambiente (prompt 41)

| Variável | Obrigatória | Padrão | Significado |
|---|---|---|---|
| `OS_AMBIENTE` | não | vazio | Nome do ambiente (`producao`, `homologacao`, `desenvolvimento`). Com `producao`, o comando `preparar-piloto` exige um segundo aviso (`--sei-que-e-producao`). |

## Fora do app

| Variável | Onde | Significado |
|---|---|---|
| `PORT` | `docker/iniciar.sh` | Porta do servidor no contêiner (padrão 8000). Num servidor próprio, a porta vai na linha do uvicorn (docs/IMPLANTACAO_LOCAL.md). |
| `OS_TEST_DATABASE_URL` | testes | Banco PostgreSQL vazio para rodar a suíte nele. Nunca o de produção. |
| `FLET_*` | biblioteca Flet | Lidas pela própria Flet (por exemplo `FLET_WEB_APP_PATH`). O app não as usa; não defina sem necessidade. |
