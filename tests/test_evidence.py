"""Tests for the Evidence API (Phase 8).

All tests use AsyncMock — no live PostgreSQL required.
"""

import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.security import create_access_token
from app.database import get_db
from app.main import app

CAMPO_USER_ID = uuid.uuid4()
EVIDENCE_ID = uuid.uuid4()
INCIDENT_ID = uuid.uuid4()


def make_fake_campo() -> MagicMock:
    user = MagicMock()
    user.id = CAMPO_USER_ID
    user.name = "Campo Test"
    user.email = "campo@test.com"
    user.role = "campo"
    user.is_active = True
    user.created_at = datetime.datetime.now(datetime.UTC)
    user.updated_at = user.created_at
    return user


def make_fake_evidence(evidence_id: uuid.UUID | None = None) -> MagicMock:
    ev = MagicMock()
    ev.id = evidence_id or EVIDENCE_ID
    ev.incident_id = INCIDENT_ID
    ev.report_id = None
    ev.type = "photo"
    ev.url = "https://storage.example.com/evidence/foto1.jpg"
    ev.description = "Fotografia do foco de incêndio"
    ev.latitude = -15.5
    ev.longitude = -55.8
    ev.location = None  # no PostGIS in tests
    ev.source = "campo"
    ev.created_at = datetime.datetime.now(datetime.UTC)
    return ev


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_evidence_requires_auth(client):
    """GET /api/v1/evidence without token — should return 401 or 403."""
    response = await client.get("/api/v1/evidence")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_evidence_not_found(client):
    """GET /api/v1/evidence/{id} with valid campo token, DB returns None → 404."""
    mock_db = AsyncMock()
    fake_campo = make_fake_campo()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_campo

    not_found_result = MagicMock()
    not_found_result.scalar_one_or_none.return_value = None

    mock_db.execute.side_effect = [user_result, not_found_result]
    mock_db.commit = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        token = create_access_token(str(CAMPO_USER_ID), "campo")
        response = await client.get(
            f"/api/v1/evidence/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_evidence_with_campo(client):
    """POST /api/v1/evidence with campo token, DB mocked → 201 with expected fields."""
    mock_db = AsyncMock()
    fake_campo = make_fake_campo()
    fake_evidence = make_fake_evidence()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_campo
    mock_db.execute.return_value = user_result
    mock_db.commit = AsyncMock()

    def _inject_fields(obj):
        from app.evidence.model import Evidence

        if isinstance(obj, Evidence):
            obj.id = fake_evidence.id
            obj.created_at = fake_evidence.created_at
            # Evidence has no updated_at — immutable

    mock_db.add = MagicMock(side_effect=_inject_fields)
    mock_db.flush = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        token = create_access_token(str(CAMPO_USER_ID), "campo")
        response = await client.post(
            "/api/v1/evidence",
            json={
                "incident_id": str(INCIDENT_ID),
                "type": "photo",
                "url": "https://storage.example.com/evidence/foto1.jpg",
                "description": "Fotografia do foco de incêndio",
                "latitude": -15.5,
                "longitude": -55.8,
                "source": "campo",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "photo"
        assert data["url"] == "https://storage.example.com/evidence/foto1.jpg"
        assert data["incident_id"] == str(INCIDENT_ID)
        assert "id" in data
        assert "created_at" in data
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_evidence_requires_campo(client):
    """POST /api/v1/evidence without token — should return 401 or 403."""
    response = await client.post(
        "/api/v1/evidence",
        json={
            "type": "photo",
            "url": "https://example.com/foto.jpg",
        },
    )
    assert response.status_code in (401, 403)
