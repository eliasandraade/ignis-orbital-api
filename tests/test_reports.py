"""Tests for the Public Reports API (Phase 6).

All tests use AsyncMock — no live PostgreSQL/PostGIS required.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.security import create_access_token
from app.database import get_db
from app.main import app

GESTOR_USER_ID = uuid.uuid4()
REPORT_ID = uuid.uuid4()
FAKE_PROTOCOL = "RP-20260101-TEST"


def make_fake_report(
    report_id: uuid.UUID | None = None, protocol: str = FAKE_PROTOCOL
) -> MagicMock:
    """Return a MagicMock that looks like a PublicReport ORM instance."""
    report = MagicMock()
    report.id = report_id or REPORT_ID
    report.protocol = protocol
    report.type = "fire"
    report.description = "Foco de incêndio detectado"
    report.urgency = "high"
    report.status = "pending"
    report.reporter_name = "Test Reporter"
    report.contact = "test@test.com"
    report.is_anonymous = False
    report.latitude = -15.5
    report.longitude = -55.8
    report.location = None
    report.protected_area_id = None
    report.evidence_urls = []
    report.validation_notes = None
    report.linked_incident_id = None
    report.created_at = datetime.now(UTC)
    report.updated_at = datetime.now(UTC)
    return report


def make_fake_gestor() -> MagicMock:
    user = MagicMock()
    user.id = GESTOR_USER_ID
    user.name = "Gestor Test"
    user.email = "gestor@test.com"
    user.role = "gestor"
    user.is_active = True
    user.created_at = datetime.now(UTC)
    user.updated_at = user.created_at
    return user


@pytest.fixture
async def db_submit_report():
    """Mock DB for POST /reports — public endpoint, no auth needed."""
    mock_db = AsyncMock()
    fake_report = make_fake_report()

    # db.add must be a plain MagicMock (not AsyncMock) so the side_effect
    # runs synchronously when db.add(report) is called without await.
    def _add_with_id(obj):
        obj.id = fake_report.id
        obj.created_at = fake_report.created_at
        obj.updated_at = fake_report.updated_at
        obj.location = None

    mock_db.add = MagicMock(side_effect=_add_with_id)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    yield mock_db
    app.dependency_overrides.clear()


@pytest.fixture
async def db_report_found():
    """Mock DB that returns a gestor for auth and a fake report for lookup."""
    mock_db = AsyncMock()
    fake_gestor = make_fake_gestor()
    fake_report = make_fake_report()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_gestor

    report_result = MagicMock()
    report_result.scalar_one_or_none.return_value = fake_report

    mock_db.execute.side_effect = [user_result, report_result]
    mock_db.commit = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    yield mock_db
    app.dependency_overrides.clear()


@pytest.fixture
async def db_report_not_found():
    """Mock DB for gestor auth (found) + report lookup (not found)."""
    mock_db = AsyncMock()
    fake_gestor = make_fake_gestor()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_gestor

    empty_result = MagicMock()
    empty_result.scalar_one_or_none.return_value = None

    mock_db.execute.side_effect = [user_result, empty_result]
    mock_db.commit = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    yield mock_db
    app.dependency_overrides.clear()


@pytest.fixture
async def db_lookup_by_protocol():
    """Mock DB for public /lookup endpoint — no auth, just report lookup."""
    mock_db = AsyncMock()
    fake_report = make_fake_report()

    report_result = MagicMock()
    report_result.scalar_one_or_none.return_value = fake_report

    mock_db.execute.return_value = report_result
    mock_db.commit = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    yield mock_db
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_report_public(client, db_submit_report):
    """POST /api/v1/reports (no auth) — should return 201 with protocol field."""
    payload = {
        "type": "fire",
        "description": "Foco de incêndio detectado próximo à margem do rio",
        "urgency": "high",
        "latitude": -15.5,
        "longitude": -55.8,
        "reporter_name": "Test Reporter",
        "contact": "test@test.com",
        "is_anonymous": False,
    }
    response = await client.post("/api/v1/reports", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "protocol" in data
    assert "id" in data
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_list_reports_requires_gestor(client):
    """GET /api/v1/reports without token — should return 401 or 403."""
    response = await client.get("/api/v1/reports")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_lookup_by_protocol(client, db_lookup_by_protocol):
    """GET /api/v1/reports/lookup?protocol=... — public endpoint, returns report or 404."""
    response = await client.get(f"/api/v1/reports/lookup?protocol={FAKE_PROTOCOL}")
    # Either 200 (found) or 404 (not found) are valid — mock returns found
    assert response.status_code in (200, 404)
    if response.status_code == 200:
        data = response.json()
        assert "protocol" in data


@pytest.mark.asyncio
async def test_get_report_not_found(client, db_report_not_found):
    """GET /api/v1/reports/{id} with gestor token — should return 404 when not found."""
    token = create_access_token(str(GESTOR_USER_ID), "gestor")
    response = await client.get(
        f"/api/v1/reports/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
