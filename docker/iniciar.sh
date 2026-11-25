#!/bin/sh
# Inicialização do contêiner: cria os dados fictícios (opcional) e sobe o servidor ASGI
# com um único processo (as sessões ficam na memória).
# As migrações NÃO rodam aqui: o responsável roda `alembic upgrade head` à mão, depois de
# um backup (docs/NUVEM.md, "Migrações").
set -e
# O banco de produção é PostgreSQL: SQLite num contêiner perde tudo a cada reinício.
case "${OS_DATABASE_URL:-}" in
    sqlite*) echo "Erro: OS_DATABASE_URL aponta para SQLite; use PostgreSQL." >&2; exit 1 ;;
esac
# O seed (dados iniciais e de demonstração) é opcional: uma falha nele não impede o app
# de subir; o motivo fica no log.
if [ -n "${OS_SEED_SENHA:-}" ]; then
    python -m osapp.seed || echo "ERRO: o seed não foi executado; o motivo está na linha anterior do log." >&2
fi
# O IP do cliente é resolvido pelo próprio app (osapp/rede.py), que só aceita cabeçalhos
# de encaminhamento vindos de OS_PROXIES_CONFIAVEIS. Por isso o uvicorn roda sem
# --proxy-headers. --no-access-log: o log de acesso gravaria o IP de cada pedido.
exec uvicorn osapp.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
    --no-proxy-headers --no-access-log
