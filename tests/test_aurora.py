"""Tests for the Aurora IA rule-based engine and API (Phase 9).

Aurora endpoints are pure Python — no DB mocking needed.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.security import create_access_token
from app.database import get_db
from app.main import app

CAMPO_USER_ID = uuid.uuid4()


def make_fake_campo() -> MagicMock:
    user = MagicMock()
    user.id = CAMPO_USER_ID
    user.name = "Campo Test"
    user.email = "campo@test.com"
    user.role = "campo"
    user.is_active = True
    return user


# ---------------------------------------------------------------------------
# Chat tests (public endpoint — no auth needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_incendio(client):
    """POST /api/v1/aurora/chat with fire-related message → 200, response contains fire guidance."""
    response = await client.post(
        "/api/v1/aurora/chat",
        json={"message": "incêndio na reserva"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert len(data["response"]) > 0
    assert "confidence" in data
    assert data["confidence"] > 0.0
    assert isinstance(data["suggested_actions"], list)


@pytest.mark.asyncio
async def test_chat_default(client):
    """POST /api/v1/aurora/chat with unknown message → 200, default Aurora response."""
    response = await client.post(
        "/api/v1/aurora/chat",
        json={"message": "xyzzy qualquer coisa aleatória"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "Aurora" in data["response"]
    assert data["confidence"] == 0.5
    assert isinstance(data["suggested_actions"], list)
    assert len(data["suggested_actions"]) > 0


# ---------------------------------------------------------------------------
# Analyze tests (requires campo role)
# ---------------------------------------------------------------------------


def _campo_override(fake_campo: MagicMock):
    """Return a dependency override that injects a fake campo user without hitting the DB."""
    mock_db = AsyncMock()
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_campo
    mock_db.execute.return_value = user_result

    async def override_get_db():
        yield mock_db

    return override_get_db


@pytest.mark.asyncio
async def test_analyze_critical(client):
    """POST /api/v1/aurora/analyze with critical severity + extreme conditions → critical risk."""
    fake_campo = make_fake_campo()
    app.dependency_overrides[get_db] = _campo_override(fake_campo)
    try:
        token = create_access_token(str(CAMPO_USER_ID), "campo")
        response = await client.post(
            "/api/v1/aurora/analyze",
            json={
                "incident_severity": "critical",
                "incident_type": "fire",
                "wind_speed": 55.0,
                "humidity": 20.0,
                "area_hectares": 200.0,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["risk_level"] == "critical"
        assert data["priority_score"] >= 90
        assert isinstance(data["recommended_actions"], list)
        assert len(data["recommended_actions"]) >= 3
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_analyze_low_risk(client):
    """POST /api/v1/aurora/analyze with low severity → risk_level=low."""
    fake_campo = make_fake_campo()
    app.dependency_overrides[get_db] = _campo_override(fake_campo)
    try:
        token = create_access_token(str(CAMPO_USER_ID), "campo")
        response = await client.post(
            "/api/v1/aurora/analyze",
            json={"incident_severity": "low"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["risk_level"] == "low"
        assert data["priority_score"] < 50
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_analyze_spread_fire(client):
    """POST /api/v1/aurora/analyze with fire + wind_speed → estimated_spread_km2 is not None."""
    fake_campo = make_fake_campo()
    app.dependency_overrides[get_db] = _campo_override(fake_campo)
    try:
        token = create_access_token(str(CAMPO_USER_ID), "campo")
        response = await client.post(
            "/api/v1/aurora/analyze",
            json={
                "incident_type": "fire",
                "wind_speed": 40.0,
                "humidity": 50.0,
                "area_hectares": 100.0,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["estimated_spread_km2"] is not None
        assert data["estimated_spread_km2"] > 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_analyze_requires_auth(client):
    """POST /api/v1/aurora/analyze without token → 401 or 403."""
    response = await client.post(
        "/api/v1/aurora/analyze",
        json={"incident_severity": "low"},
    )
    assert response.status_code in (401, 403)
