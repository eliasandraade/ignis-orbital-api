from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.main import app


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
