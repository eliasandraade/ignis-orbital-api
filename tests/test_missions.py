"""Tests for the Missions API (Phase 8).

All tests use AsyncMock — no live PostgreSQL required.
"""

import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.security import create_access_token
from app.database import get_db
from app.main import app

GESTOR_USER_ID = uuid.uuid4()
MISSION_ID = uuid.uuid4()
INCIDENT_ID = uuid.uuid4()
TEAM_ID = uuid.uuid4()


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


def make_fake_mission(mission_id: uuid.UUID | None = None) -> MagicMock:
    mission = MagicMock()
    mission.id = mission_id or MISSION_ID
    mission.incident_id = INCIDENT_ID
    mission.team_id = TEAM_ID
    mission.status = "planned"
    mission.objective = "Combater incêndio no setor norte"
    mission.notes = None
    mission.started_at = None
    mission.completed_at = None
    mission.created_at = datetime.datetime.now(datetime.UTC)
    mission.updated_at = mission.created_at
    return mission


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_missions_requires_auth(client):
    """GET /api/v1/missions without token — should return 401 or 403."""
    response = await client.get("/api/v1/missions")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_mission_not_found(client):
    """GET /api/v1/missions/{id} with valid gestor token, DB returns None → 404."""
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
            f"/api/v1/missions/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_mission_with_gestor(client):
    """POST /api/v1/missions with gestor token, DB mocked → 201 with expected fields."""
    mock_db = AsyncMock()
    fake_gestor = make_fake_gestor()
    fake_mission = make_fake_mission()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_gestor
    mock_db.execute.return_value = user_result
    mock_db.commit = AsyncMock()

    def _inject_fields(obj):
        from app.missions.model import Mission

        if isinstance(obj, Mission):
            obj.id = fake_mission.id
            obj.created_at = fake_mission.created_at
            obj.updated_at = fake_mission.updated_at

    mock_db.add = MagicMock(side_effect=_inject_fields)
    mock_db.flush = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        token = create_access_token(str(GESTOR_USER_ID), "gestor")
        response = await client.post(
            "/api/v1/missions",
            json={
                "incident_id": str(INCIDENT_ID),
                "team_id": str(TEAM_ID),
                "objective": "Combater incêndio no setor norte",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["objective"] == "Combater incêndio no setor norte"
        assert data["status"] == "planned"
        assert data["incident_id"] == str(INCIDENT_ID)
        assert data["team_id"] == str(TEAM_ID)
        assert "id" in data
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_mission_requires_gestor(client):
    """POST /api/v1/missions without token — should return 401 or 403."""
    response = await client.post(
        "/api/v1/missions",
        json={
            "incident_id": str(uuid.uuid4()),
            "team_id": str(uuid.uuid4()),
            "objective": "Test",
        },
    )
    assert response.status_code in (401, 403)
