import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(client_no_db):
    response = await client_no_db.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_structure(client_no_db):
    response = await client_no_db.get("/health")
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "ignis-orbital-api"
    assert "version" in data
    assert "environment" in data


@pytest.mark.asyncio
async def test_ready_fails_without_database(client_no_db):
    """
    /ready deve retornar 503 quando o banco não está disponível.
    Em CI sem banco, o comportamento esperado é falha controlada.
    """
    response = await client_no_db.get("/ready")
    assert response.status_code == 503
