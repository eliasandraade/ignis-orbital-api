#!/bin/bash
# Usage: entrypoint.sh [api|migrate]
#   api      (default) wait for the database, optionally migrate, run the demo
#            seed where allowed, then serve HTTP.
#   migrate  wait for the database, apply migrations and exit. Railway runs it
#            as the pre-deploy command: once per deploy, before any replica of
#            the new version starts, and a failure aborts the deploy.
set -euo pipefail

# A platform may either replace the image ENTRYPOINT with the configured
# command or pass that command as arguments to it; accept both forms.
if [[ "${1:-}" == "$0" || "${1:-}" == "/app/scripts/entrypoint.sh" ]]; then
    shift
fi
ROLE="${1:-api}"

# Fail closed: without an explicit APP_ENV the API would default to
# "development", where demo data and the development JWT secret are allowed.
: "${APP_ENV:?APP_ENV deve ser definido (development|test|demo|staging|production)}"

wait_for_database() {
    local attempts="${DB_WAIT_ATTEMPTS:-60}"
    # Invalid configuration (weak secret, wrong environment, unsafe CORS) must
    # fail loudly here, not be retried as if the database were down.
    python -c "from app.config import get_settings; get_settings()"
    echo "==> [IGNIS Orbital API] Aguardando banco de dados..."
    for ((i = 1; i <= attempts; i++)); do
        # Settings normalizes the URL (postgres:// from Railway → asyncpg dialect).
        if python -c "
import asyncio
import asyncpg
from app.config import get_settings

async def check():
    url = get_settings().database_url.replace('postgresql+asyncpg://', 'postgresql://')
    conn = await asyncpg.connect(url, timeout=5)
    await conn.close()

asyncio.run(check())
" 2>/dev/null; then
            echo "==> [IGNIS Orbital API] Banco disponível."
            return 0
        fi
        echo "    Banco ainda não pronto (${i}/${attempts}), tentando novamente em 2s..."
        sleep 2
    done
    # Bounded: a pre-deploy command has no default timeout on Railway.
    echo "==> [IGNIS Orbital API] Banco indisponível; abortando." >&2
    return 1
}

migrate() {
    echo "==> [IGNIS Orbital API] Aplicando migrations..."
    alembic upgrade head
}

case "$ROLE" in
    migrate)
        wait_for_database
        migrate
        ;;
    api)
        wait_for_database
        # Railway migrates in the pre-deploy step (MIGRATE_ON_START=false), so
        # replicas never race on Alembic. Local/compose keeps the old behaviour.
        if [[ "${MIGRATE_ON_START:-true}" == "true" ]]; then
            migrate
        fi

        # The demo seed creates users with published passwords. Python decides from
        # APP_ENV (development/test/demo only); staging/production are always skipped.
        python -m seed --if-allowed

        echo "==> [IGNIS Orbital API] Iniciando servidor..."
        # --reload only for local development: a reachable deploy (demo/staging/production)
        # must never re-execute code written at runtime.
        if [[ "$APP_ENV" == "development" ]]; then
            exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
        else
            exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
                --workers "${WEB_CONCURRENCY:-2}" --proxy-headers
        fi
        ;;
    *)
        echo "Papel desconhecido: '$ROLE' (use api ou migrate)" >&2
        exit 64
        ;;
esac
