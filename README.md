# Sistema de OS

Aplicativo web de ordens de serviço (OS) para equipes de manutenção e operação.
Flet 1.1 rodando no servidor: o Python roda no servidor e o navegador mostra a interface.

Documentos: [regras do projeto](docs/REGRAS.md) · [estado atual](docs/ESTADO.md) ·
[auditoria de segurança](docs/AUDITORIA.md) · [próximos passos](docs/PROXIMOS_PASSOS.md) ·
[publicar na nuvem sem custo](docs/NUVEM.md).

## Requisitos

- Linux, Python 3.12 ou mais novo.
- SQLite (já vem com o Python) para desenvolvimento.
- Um navegador atual. Celulares são o alvo principal.

## Início rápido

```bash
OS_SEED_SENHA='uma-senha-de-teste' ./executar.sh    # prepara tudo e abre http://localhost:8550
```

O script cria o ambiente virtual, instala as dependências, cria o `.env` e as tabelas e
inicia o app em modo de desenvolvimento. Sem `OS_SEED_SENHA`, não cria os usuários
fictícios. Os passos manuais equivalentes estão abaixo.

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env      # ajuste os valores; o .env nunca vai para o git
```

## Variáveis de ambiente

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `OS_DATABASE_URL` | sim | — | URL do banco (SQLAlchemy). Não há padrão no código. |
| `OS_TZ` | não | `America/Sao_Paulo` | Fuso de exibição e de digitação de datas (IANA). |
| `OS_SESSAO_TIMEOUT_MIN` | não | `30` | Minutos sem atividade até encerrar a sessão. |
| `OS_LOG_LEVEL` | não | `INFO` | DEBUG, INFO, WARNING, ERROR ou CRITICAL. |
| `OS_SEED_SENHA` | só no seed | — | Senha dos usuários fictícios (mínimo 8 caracteres). |
| `OS_TEST_DATABASE_URL` | não | — | Banco alternativo para os testes. |

Se uma variável obrigatória faltar ou um valor for inválido, o app encerra na inicialização
com uma mensagem clara. Um arquivo `.env` local é lido em desenvolvimento.

## Banco de dados (migração)

```bash
alembic upgrade head      # cria ou atualiza as tabelas
alembic check             # confere se modelos e migrações concordam
```

O Alembic lê a URL de `OS_DATABASE_URL`, nunca do `alembic.ini`.

## Dados fictícios (seed)

```bash
OS_SEED_SENHA='uma-senha-de-teste' python -m osapp.seed
```

Cria as filiais F001 e F002 e os usuários `admin`, `marina.teste`, `joao.ficticio` (F001) e
`carlos.exemplo` (F002), todos com a senha de `OS_SEED_SENHA`. Pode ser executado mais de
uma vez. Não use o seed em produção.

## Executar em desenvolvimento

```bash
python -m osapp.main      # http://localhost:8550
```

## Executar em produção

O app é uma aplicação ASGI, `osapp.main:app`. O uvicorn já vem com `flet[web]`:

```bash
uvicorn osapp.main:app --host 127.0.0.1 --port 8000
```

Regras para produção:

- **Sempre atrás de um proxy reverso com HTTPS** (nginx, Caddy, ou o balanceador da nuvem).
  O app fala HTTP simples e não deve ser exposto assim fora de uma rede de teste: senhas e
  dados passariam sem criptografia. Escute em `127.0.0.1` e deixe só o proxy acessível.
- O proxy precisa repassar **WebSocket** (cabeçalhos `Upgrade` e `Connection`) no caminho `/ws`.
- As sessões ficam na memória do processo: use **um único worker**, ou sessões fixas
  (sticky) no balanceador. Reiniciar o processo encerra as sessões.
- Crie os usuários reais com a CLI, não com o seed.

Exemplo mínimo de nginx (o certificado fica por conta do ambiente):

```nginx
server {
    listen 443 ssl;
    server_name os.exemplo.invalid;
    # ssl_certificate e ssl_certificate_key aqui

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

### Contêiner e nuvem

Há um `Dockerfile` (app + driver PostgreSQL) e um `render.yaml`. O passo a passo para
publicar sem custo (Render + Neon) está em [docs/NUVEM.md](docs/NUVEM.md). Para usar
PostgreSQL fora do contêiner: `pip install -e '.[postgres]'`; URLs `postgres://` e
`postgresql://` são aceitas e passam a usar o driver psycopg.

## CLI de administração

Senhas são sempre pedidas no terminal (nunca passadas como argumento).

```bash
python -m osapp.cli criar-filial --codigo F003 --nome 'Filial Modelo Oeste'
python -m osapp.cli criar-usuario                       # pergunta nome, login, filial e senha
python -m osapp.cli criar-usuario --nome 'Ana Modelo' --login ana.modelo --filial F001 --admin
python -m osapp.cli redefinir-senha --login ana.modelo  # também remove o bloqueio
python -m osapp.cli desativar-usuario --login ana.modelo
```

## Testes e qualidade

```bash
ruff check .
pytest -q
```

Cada teste usa um SQLite temporário novo. Para rodar os mesmos testes em outro banco (por
exemplo PostgreSQL, com o driver instalado), defina `OS_TEST_DATABASE_URL`; esse banco é
esvaziado a cada teste.

## Como o app funciona, em resumo

- Camadas: `models -> repositories -> services -> ui`. Regras de negócio e permissões ficam
  só em `services`; a interface nunca importa modelos nem repositórios.
- Uma OS passa por Aberta -> Em execução -> Concluída. Qualquer usuário da filial inicia; só
  quem iniciou (ou um administrador) conclui ou desfaz o início.
- Usuário comum trabalha só na própria filial; administrador vê e age em todas.
- Toda criação, edição e mudança de status entra no histórico da OS, que nunca é alterado.
- Dinheiro é guardado em centavos, durações em minutos e instantes em UTC.
