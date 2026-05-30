#!/bin/bash
set -e

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

echo "==> [IGNIS Orbital API] Aplicando seed demonstrativo..."
python -m seed

echo "==> [IGNIS Orbital API] Iniciando servidor..."
if [ "${APP_ENV:-development}" = "production" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
else
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
fi
