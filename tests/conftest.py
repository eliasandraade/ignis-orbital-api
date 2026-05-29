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
    Cliente que sobrescreve a dependência get_db com um stub que lança erro.
    Use para testar endpoints que NÃO devem precisar de banco.
    """

    async def _no_db():
        raise RuntimeError("Banco não disponível neste contexto de teste")
        yield  # noqa: unreachable — necessário para ser generator

    app.dependency_overrides[get_db] = _no_db
    yield client
    app.dependency_overrides.clear()
