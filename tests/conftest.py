from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.rate_limit import reset_rate_limits
from app.database import get_db
from app.integrations._cache import cache_clear
from app.main import app


@pytest.fixture(autouse=True)
def _isolate_process_state():
    """In-memory caches and rate-limit counters must not leak between tests."""
    cache_clear()
    reset_rate_limits()
    yield
    cache_clear()
    reset_rate_limits()
    app.dependency_overrides.clear()


@pytest.fixture
async def client():
    """Cliente HTTP assíncrono sem banco de dados — para testes de unidade."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
async def client_no_db(client):
    """
    Cliente que injeta uma sessão mock que falha ao executar queries.
    Permite testar que endpoints lidam corretamente com falhas de banco.
    """

    async def _failing_db():
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("Banco não disponível neste contexto de teste")
        yield mock_session

    app.dependency_overrides[get_db] = _failing_db
    yield client
    app.dependency_overrides.clear()


# --- PostGIS integration (tests/postgis.py) ---------------------------------


@pytest.fixture(scope="session")
def geo_database():
    """A migrated database with the official IBGE boundaries imported once."""
    from tests import postgis

    postgis.require_postgis()
    name = postgis.create_database()
    try:
        postgis.alembic("upgrade", "head", database=name)
        result = postgis.run_module("seed.jurisdictions", database=name)
        assert result.returncode == 0, result.stderr
        yield name
    finally:
        postgis.drop_database(name)


@pytest.fixture
async def geo_engine(geo_database):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from tests import postgis

    engine = create_async_engine(postgis.asyncpg_url(geo_database), poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def clean_orbital(geo_engine):
    """Detections and runs start empty; the boundaries stay."""
    from sqlalchemy import text

    async with geo_engine.begin() as conn:
        await conn.execute(text("TRUNCATE orbital_detections, ingestion_runs"))
    return geo_engine
