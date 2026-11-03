#!/bin/bash
set -euo pipefail

# Fail closed: without an explicit APP_ENV the API would default to
# "development", where demo data and the development JWT secret are allowed.
: "${APP_ENV:?APP_ENV deve ser definido (development|test|demo|staging|production)}"

echo "==> [IGNIS Orbital API] Aguardando banco de dados..."
until python -c "
import asyncio
import asyncpg
import os

async def check():
    conn = await asyncpg.connect(os.environ['DATABASE_URL'].replace('postgresql+asyncpg://', 'postgresql://'))
    await conn.close()

asyncio.run(check())
" 2>/dev/null; do
    echo "    Banco ainda não pronto, tentando novamente em 2s..."
    sleep 2
done

echo "==> [IGNIS Orbital API] Banco disponível. Aplicando migrations..."
alembic upgrade head

# The demo seed creates users with published passwords. Python decides from
# APP_ENV (development/test/demo only); staging/production are always skipped.
python -m seed --if-allowed

echo "==> [IGNIS Orbital API] Iniciando servidor..."
if [[ "$APP_ENV" == "production" || "$APP_ENV" == "staging" ]]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 2 --proxy-headers
else
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
fi
