# Imagem do Sistema de OS (app ASGI). Banco: PostgreSQL, via OS_DATABASE_URL.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY migrations ./migrations
COPY docker/iniciar.sh /usr/local/bin/iniciar

RUN pip install '.[postgres]' \
    && useradd --create-home app \
    && chown -R app /app
USER app

EXPOSE 8000
CMD ["iniciar"]
