#!/bin/sh
# Inicialização do contêiner: atualiza o banco, cria os dados fictícios (opcional) e
# sobe o servidor ASGI com um único processo (as sessões ficam na memória).
set -e
alembic upgrade head
if [ -n "${OS_SEED_SENHA:-}" ]; then
    python -m osapp.seed
fi
# --proxy-headers: o contêiner fica atrás do proxy HTTPS da plataforma.
exec uvicorn osapp.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
    --proxy-headers --forwarded-allow-ips '*'
