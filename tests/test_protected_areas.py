"""Tests for the Protected Areas API (Phase 5).

All tests use AsyncMock — no live PostgreSQL/PostGIS required.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.security import create_access_token
from app.database import get_db
from app.main import app

ADMIN_USER_ID = uuid.uuid4()
ORGAO_USER_ID = uuid.uuid4()
AREA_ID = uuid.uuid4()


def make_fake_area(area_id: uuid.UUID | None = None) -> MagicMock:
    """Return a MagicMock that looks like a ProtectedArea ORM instance."""
    area = MagicMock()
    area.id = area_id or AREA_ID
    area.name = "APA Chapada dos Guimarães"
    area.category = "APA"
    area.municipality = "Chapada dos Guimarães"
    area.state = "MT"
    area.organ = "ICMBio"
    area.area_ha = 325_000.0
    area.source = "base demonstrativa acadêmica"
    area.data_quality = "estimated"
    area.confidence = 0.5
    area.center_lat = -15.5
    area.center_lng = -55.8
    area.geometry = None
    area.buffer_zone = None
    area.created_at = datetime.now(UTC)
    area.updated_at = datetime.now(UTC)
    return area


def make_fake_admin(role: str = "admin") -> MagicMock:
    user = MagicMock()
    user.id = ADMIN_USER_ID
    user.name = "Admin Test"
    user.email = "admin@test.com"
    user.role = role
    user.is_active = True
    user.created_at = datetime.now(UTC)
    user.updated_at = user.created_at
    return user


@pytest.fixture
async def db_areas():
    """Mock DB that returns a list with one fake area and supports count."""
    mock_db = AsyncMock()
    fake_area = make_fake_area()

    # count result
    count_result = MagicMock()
    count_result.scalar_one.return_value = 1

    # scalars result
    scalars_result = MagicMock()
    scalars_result.scalars.return_value.all.return_value = [fake_area]

    # execute returns count then list — use side_effect to alternate
    mock_db.execute.side_effect = [count_result, scalars_result]
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    yield mock_db
    app.dependency_overrides.clear()


@pytest.fixture
async def db_area_not_found():
    """Mock DB that returns None for any scalar_one_or_none lookup."""
    mock_db = AsyncMock()

    empty_result = MagicMock()
    empty_result.scalar_one_or_none.return_value = None

    mock_db.execute.return_value = empty_result
    mock_db.commit = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    yield mock_db
    app.dependency_overrides.clear()


@pytest.fixture
async def db_create_area():
    """
    Mock DB for POST /protected-areas.
    Two execute() calls happen in service.create_area (just flush) and
    two more in get_current_user (user lookup). We handle all via side_effect.
    """
    mock_db = AsyncMock()
    fake_area = make_fake_area()
    fake_admin = make_fake_admin()

    # get_current_user does execute(select(User)...) → returns admin
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_admin

    mock_db.execute.return_value = user_result
    mock_db.commit = AsyncMock()
    mock_db.flush = AsyncMock()

    # db.add must be a plain MagicMock (not AsyncMock) so the side_effect
    # runs synchronously when db.add(area) is called without await.
    def _add_with_id(obj):
        obj.id = fake_area.id
        obj.created_at = fake_area.created_at
        obj.updated_at = fake_area.updated_at
        obj.geometry = None
        obj.buffer_zone = None

    mock_db.add = MagicMock(side_effect=_add_with_id)

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    yield mock_db
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_areas_public(client, db_areas):
    """GET /api/v1/protected-areas — public endpoint, should return 200."""
    response = await client.get("/api/v1/protected-areas")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "APA Chapada dos Guimarães"


@pytest.mark.asyncio
async def test_get_area_not_found(client, db_area_not_found):
    """GET /api/v1/protected-areas/{id} with unknown id — should return 404."""
    response = await client.get(f"/api/v1/protected-areas/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_area_requires_orgao(client):
    """POST /api/v1/protected-areas without auth token — should return 401 or 403."""
    payload = {
        "name": "Parque Nacional da Tijuca",
        "category": "PARNA",
        "municipality": "Rio de Janeiro",
        "state": "RJ",
        "organ": "ICMBio",
        "area_ha": 3953.0,
        "center_lat": -22.93,
        "center_lng": -43.28,
    }
    response = await client.post("/api/v1/protected-areas", json=payload)
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_create_area_with_admin_token(client, db_create_area):
    """POST /api/v1/protected-areas with admin JWT — should return 201."""
    token = create_access_token(str(ADMIN_USER_ID), "admin")
    payload = {
        "name": "APA Chapada dos Guimarães",
        "category": "APA",
        "municipality": "Chapada dos Guimarães",
        "state": "MT",
        "organ": "ICMBio",
        "area_ha": 325000.0,
        "center_lat": -15.5,
        "center_lng": -55.8,
    }
    response = await client.post(
        "/api/v1/protected-areas",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "APA Chapada dos Guimarães"
    assert data["state"] == "MT"
    assert "id" in data
