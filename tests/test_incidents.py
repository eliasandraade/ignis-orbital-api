"""Tests for the Incidents API (Phase 7).

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
INCIDENT_ID = uuid.uuid4()
AREA_ID = uuid.uuid4()


def make_fake_gestor(role: str = "gestor") -> MagicMock:
    user = MagicMock()
    user.id = GESTOR_USER_ID
    user.name = "Gestor Test"
    user.email = "gestor@test.com"
    user.role = role
    user.is_active = True
    user.created_at = datetime.now(UTC)
    user.updated_at = user.created_at
    return user


def make_fake_incident(incident_id: uuid.UUID | None = None) -> MagicMock:
    """Return a MagicMock that looks like an Incident ORM instance."""
    inc = MagicMock()
    inc.id = incident_id or INCIDENT_ID
    inc.code = "IGN-CE-2026-0001"
    inc.title = "Incêndio na APA Chapada"
    inc.type = "fire"
    inc.severity = "high"
    inc.status = "active"
    inc.protected_area_id = AREA_ID
    inc.latitude = -15.5
    inc.longitude = -55.8
    inc.location = None  # no PostGIS in tests
    inc.source = "sensor"
    inc.confidence = 0.9
    inc.affected_hectares = 50.0
    inc.wind_direction = "NE"
    inc.wind_speed = 30.0
    inc.humidity = 20.0
    inc.temperature = 38.0
    inc.detected_at = datetime.now(UTC)
    inc.created_at = datetime.now(UTC)
    inc.updated_at = datetime.now(UTC)
    return inc


def make_fake_event(incident_id: uuid.UUID | None = None) -> MagicMock:
    ev = MagicMock()
    ev.id = uuid.uuid4()
    ev.incident_id = incident_id or INCIDENT_ID
    ev.type = "observation"
    ev.actor_id = GESTOR_USER_ID
    ev.actor_name = "Gestor Test"
    ev.description = "Incêndio se alastrou para o setor norte"
    ev.timestamp = datetime.now(UTC)
    return ev


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_gestor_only():
    """Mock DB that only serves the gestor user lookup (for auth)."""
    mock_db = AsyncMock()
    fake_gestor = make_fake_gestor()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_gestor
    mock_db.execute.return_value = user_result
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    yield mock_db
    app.dependency_overrides.clear()


@pytest.fixture
async def db_incident_not_found():
    """Mock DB: user lookup returns gestor; incident lookup returns None."""
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
    yield mock_db
    app.dependency_overrides.clear()


@pytest.fixture
async def db_create_incident():
    """Mock DB for POST /incidents: auth lookup + add/flush side_effect."""
    mock_db = AsyncMock()
    fake_gestor = make_fake_gestor()
    fake_incident = make_fake_incident()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_gestor
    mock_db.execute.return_value = user_result

    mock_db.commit = AsyncMock()

    def _add_with_fields(obj):
        # Only set fields on Incident objects (not AuditLog)
        from app.incidents.model import Incident

        if isinstance(obj, Incident):
            obj.id = fake_incident.id
            obj.code = fake_incident.code
            obj.status = fake_incident.status
            obj.location = None
            obj.created_at = fake_incident.created_at
            obj.updated_at = fake_incident.updated_at

    mock_db.add = MagicMock(side_effect=_add_with_fields)
    mock_db.flush = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    yield mock_db
    app.dependency_overrides.clear()


@pytest.fixture
async def db_war_room_empty():
    """Mock DB for GET /war-room: two execute calls both return empty scalars."""
    mock_db = AsyncMock()
    fake_gestor = make_fake_gestor()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_gestor

    empty_incidents = MagicMock()
    empty_incidents.scalars.return_value.all.return_value = []

    empty_events = MagicMock()
    empty_events.scalars.return_value.all.return_value = []

    # Calls: (1) auth user lookup, (2) active incidents query
    # War room only calls events query when incident_ids is non-empty, so only 2 calls here
    mock_db.execute.side_effect = [user_result, empty_incidents]
    mock_db.commit = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    yield mock_db
    app.dependency_overrides.clear()


@pytest.fixture
async def db_add_event():
    """Mock DB for POST /{id}/events: auth + incident check + event add/flush."""
    mock_db = AsyncMock()
    fake_gestor = make_fake_gestor()
    fake_incident = make_fake_incident()
    fake_event = make_fake_event()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_gestor

    incident_result = MagicMock()
    incident_result.scalar_one_or_none.return_value = fake_incident

    mock_db.execute.side_effect = [user_result, incident_result]
    mock_db.commit = AsyncMock()

    def _add_event(obj):
        from app.incidents.model import IncidentEvent

        if isinstance(obj, IncidentEvent):
            obj.id = fake_event.id
            obj.incident_id = fake_event.incident_id
            obj.type = fake_event.type
            obj.actor_id = fake_event.actor_id
            obj.actor_name = fake_event.actor_name
            obj.description = fake_event.description
            obj.timestamp = fake_event.timestamp

    mock_db.add = MagicMock(side_effect=_add_event)
    mock_db.flush = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    yield mock_db
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_incidents_requires_gestor(client):
    """GET /api/v1/incidents without token — should return 401 or 403."""
    response = await client.get("/api/v1/incidents")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_incident_not_found(client, db_incident_not_found):
    """GET /api/v1/incidents/{id} with valid token but unknown id — 404."""
    token = create_access_token(str(GESTOR_USER_ID), "gestor")
    response = await client.get(
        f"/api/v1/incidents/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_incident_with_gestor(client, db_create_incident):
    """POST /api/v1/incidents with gestor token — 201 and body has 'code' field."""
    token = create_access_token(str(GESTOR_USER_ID), "gestor")
    payload = {
        "title": "Incêndio na APA Chapada",
        "type": "fire",
        "severity": "high",
        "protected_area_id": str(AREA_ID),
        "latitude": -15.5,
        "longitude": -55.8,
        "source": "sensor",
        "confidence": 0.9,
        "detected_at": datetime.now(UTC).isoformat(),
    }
    response = await client.post(
        "/api/v1/incidents",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "code" in data
    assert data["code"].startswith("IGN-CE-2026-")


@pytest.mark.asyncio
async def test_war_room_returns_summary(client, db_war_room_empty):
    """GET /api/v1/incidents/war-room with gestor token, mock empty — 200."""
    token = create_access_token(str(GESTOR_USER_ID), "gestor")
    response = await client.get(
        "/api/v1/incidents/war-room",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "active_incidents" in data
    assert "total_active" in data
    assert "by_severity" in data
    assert "latest_events" in data
    assert data["total_active"] == 0
    assert data["active_incidents"] == []


@pytest.mark.asyncio
async def test_add_event_to_incident(client, db_add_event):
    """POST /api/v1/incidents/{id}/events with gestor token — 201."""
    token = create_access_token(str(GESTOR_USER_ID), "gestor")
    payload = {
        "type": "observation",
        "description": "Incêndio se alastrou para o setor norte",
    }
    response = await client.post(
        f"/api/v1/incidents/{INCIDENT_ID}/events",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["type"] == "observation"
    assert "id" in data
    assert "timestamp" in data
