#!/usr/bin/env bash
# Prepara e inicia o Sistema de OS em modo de desenvolvimento, com um único comando.
#   ./executar.sh
# Na primeira execução cria o ambiente virtual, instala as dependências, cria o .env
# e as tabelas. Para criar também os usuários fictícios:
#   OS_SEED_SENHA='uma-senha-de-teste' ./executar.sh
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if ! "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null; then
    echo "Erro: é preciso Python 3.12 ou mais novo (comando: $PYTHON)." >&2
    exit 1
fi

if [ ! -x .venv/bin/python ]; then
    echo "Criando o ambiente virtual em .venv ..."
    "$PYTHON" -m venv .venv
fi
if ! .venv/bin/python -c 'import osapp, flet, alembic, argon2' 2>/dev/null; then
    echo "Instalando as dependências ..."
    .venv/bin/python -m pip install --quiet -e .
fi

if [ ! -f .env ] && [ -z "${OS_DATABASE_URL:-}" ]; then
    cp .env.example .env
    echo "Arquivo .env criado a partir de .env.example (banco SQLite local)."
fi

echo "Atualizando o banco de dados ..."
.venv/bin/alembic upgrade head

if [ -n "${OS_SEED_SENHA:-}" ]; then
    .venv/bin/python -m osapp.seed
fi

echo "Abrindo o app em http://localhost:8550 (Ctrl+C para parar)."
exec .venv/bin/python -m osapp.main
