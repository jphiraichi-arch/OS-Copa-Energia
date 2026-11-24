# Imagem do job de backup (prompt 36): pg_dump do PostgreSQL oficial (versão principal
# igual ou maior que a do servidor; ajuste PG_MAJOR), age e o script. Sem segredos aqui:
# tudo vem das variáveis de ambiente do job (docs/BACKUP.md).
FROM python:3.12-slim
ARG PG_MAJOR=17
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg age \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
       -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
       > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends "postgresql-client-${PG_MAJOR}" \
    && apt-get purge -y curl gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md alembic.ini ./
COPY src ./src
COPY scripts ./scripts
RUN pip install '.[postgres,backup]' && useradd --create-home backup && chown -R backup /app
USER backup
CMD ["python", "scripts/backup.py"]
