#!/bin/sh
# Inicialização do contêiner: atualiza o banco, cria os dados fictícios (opcional) e
# sobe o servidor ASGI com um único processo (as sessões ficam na memória).
set -e
alembic upgrade head
if [ -n "${OS_SEED_SENHA:-}" ]; then
    python -m osapp.seed
fi
# --proxy-headers: o contêiner fica atrás de um proxy HTTPS. Só os endereços em
# OS_PROXIES_CONFIAVEIS (IPs ou redes, separados por vírgula) podem informar o IP do
# cliente por X-Forwarded-For; de qualquer outro o cabeçalho é ignorado. Sem a variável,
# só 127.0.0.1. --no-access-log: o log de acesso do uvicorn gravaria o IP de cada pedido.
exec uvicorn osapp.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
    --proxy-headers --forwarded-allow-ips "${OS_PROXIES_CONFIAVEIS:-127.0.0.1}" \
    --no-access-log
