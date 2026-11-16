# Sistema de OS

Aplicativo web de ordens de serviço (OS) para equipes de manutenção e operação.
Flet 1.1 rodando no servidor (Python no servidor, interface no navegador).

Regras permanentes: [docs/REGRAS.md](docs/REGRAS.md). Estado atual: [docs/ESTADO.md](docs/ESTADO.md).

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env   # ajuste os valores; .env nunca vai para o git
```

## Configuração (variáveis de ambiente)

| Variável | Obrigatória | Padrão | Descrição |
|---|---|---|---|
| `OS_DATABASE_URL` | sim | — | URL do banco (SQLAlchemy). Sem valor padrão no código. |
| `OS_TZ` | não | `America/Sao_Paulo` | Fuso horário de exibição (IANA). |
| `OS_SESSAO_TIMEOUT_MIN` | não | `30` | Tempo de sessão, em minutos. |
| `OS_LOG_LEVEL` | não | `INFO` | DEBUG, INFO, WARNING, ERROR ou CRITICAL. |

Se uma variável obrigatória faltar ou um valor for inválido, o app encerra na inicialização
com uma mensagem clara.

## Executar

Desenvolvimento (abre em http://localhost:8550):

```bash
python -m osapp.main
```

Produção, como aplicação ASGI (`osapp.main:app`), com qualquer servidor ASGI. O uvicorn já
vem instalado com `flet[web]`:

```bash
uvicorn osapp.main:app --host 0.0.0.0 --port 8000
```

O app usa WebSocket e guarda as sessões na memória do processo: use um único worker (ou
sessões fixas no balanceador) e um proxy reverso que repasse WebSocket.

## Qualidade

```bash
ruff check .
pytest -q
```
