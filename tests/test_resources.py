"""Tests for the Resources API (Phase 8).

All tests use AsyncMock — no live PostgreSQL required.
"""

import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.security import create_access_token
from app.database import get_db
from app.main import app

ADMIN_USER_ID = uuid.uuid4()
GESTOR_USER_ID = uuid.uuid4()
RESOURCE_ID = uuid.uuid4()


def make_fake_admin() -> MagicMock:
    user = MagicMock()
    user.id = ADMIN_USER_ID
    user.name = "Admin Test"
    user.email = "admin@test.com"
    user.role = "admin"
    user.is_active = True
    user.created_at = datetime.datetime.now(datetime.UTC)
    user.updated_at = user.created_at
    return user


def make_fake_gestor() -> MagicMock:
    user = MagicMock()
    user.id = GESTOR_USER_ID
    user.name = "Gestor Test"
    user.email = "gestor@test.com"
    user.role = "gestor"
    user.is_active = True
    user.created_at = datetime.datetime.now(datetime.UTC)
    user.updated_at = user.created_at
    return user


def make_fake_resource(resource_id: uuid.UUID | None = None) -> MagicMock:
    res = MagicMock()
    res.id = resource_id or RESOURCE_ID
    res.name = "Caminhão Pipa"
    res.type = "vehicle"
    res.status = "available"
    res.quantity = 1
    res.location = "Base Norte"
    res.assigned_incident_id = None
    res.created_at = datetime.datetime.now(datetime.UTC)
    res.updated_at = res.created_at
    return res


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_resources_requires_auth(client):
    """GET /api/v1/resources without token — should return 401 or 403."""
    response = await client.get("/api/v1/resources")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_resource_not_found(client):
    """GET /api/v1/resources/{id} with valid gestor token, DB returns None → 404."""
    mock_db = AsyncMock()
    fake_gestor = make_fake_gestor()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_gestor

    not_found_result = MagicMock()
    not_found_result.scalar_one_or_none.return_value = None

    mock_db.execute.side_effect = [user_result, not_found_result]
    mock_db.commit = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        token = create_access_token(str(GESTOR_USER_ID), "gestor")
        response = await client.get(
            f"/api/v1/resources/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_resource_requires_admin(client):
    """POST /api/v1/resources with gestor token (not admin) — should return 403."""
    mock_db = AsyncMock()
    fake_gestor = make_fake_gestor()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_gestor
    mock_db.execute.return_value = user_result
    mock_db.commit = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        token = create_access_token(str(GESTOR_USER_ID), "gestor")
        response = await client.post(
            "/api/v1/resources",
            json={"name": "Drone Sentinel", "type": "drone"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_resource_with_admin(client):
    """POST /api/v1/resources with admin token, DB mocked → 201 with expected fields."""
    mock_db = AsyncMock()
    fake_admin = make_fake_admin()
    fake_resource = make_fake_resource()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_admin
    mock_db.execute.return_value = user_result
    mock_db.commit = AsyncMock()

    def _inject_fields(obj):
        from app.resources.model import Resource

        if isinstance(obj, Resource):
            obj.id = fake_resource.id
            obj.created_at = fake_resource.created_at
            obj.updated_at = fake_resource.updated_at

    mock_db.add = MagicMock(side_effect=_inject_fields)
    mock_db.flush = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        token = create_access_token(str(ADMIN_USER_ID), "admin")
        response = await client.post(
            "/api/v1/resources",
            json={
                "name": "Caminhão Pipa",
                "type": "vehicle",
                "status": "available",
                "quantity": 1,
                "location": "Base Norte",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Caminhão Pipa"
        assert data["type"] == "vehicle"
        assert data["status"] == "available"
        assert data["quantity"] == 1
        assert "id" in data
        assert "created_at" in data
    finally:
        app.dependency_overrides.clear()
