"""Tests for the ESG Reports API (Phase 9).

All tests use AsyncMock — no live PostgreSQL required.
"""

import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.security import create_access_token
from app.database import get_db
from app.main import app

ORGAO_USER_ID = uuid.uuid4()
ESG_REPORT_ID = uuid.uuid4()
AREA_ID = uuid.uuid4()


def make_fake_orgao() -> MagicMock:
    user = MagicMock()
    user.id = ORGAO_USER_ID
    user.name = "Orgao Test"
    user.email = "orgao@test.com"
    user.role = "orgao"
    user.is_active = True
    user.created_at = datetime.datetime.now(datetime.UTC)
    user.updated_at = user.created_at
    return user


def make_fake_esg_report(report_id: uuid.UUID | None = None) -> MagicMock:
    report = MagicMock()
    report.id = report_id or ESG_REPORT_ID
    report.protected_area_id = AREA_ID
    report.period_start = datetime.datetime(2025, 1, 1, tzinfo=datetime.UTC)
    report.period_end = datetime.datetime(2025, 3, 31, tzinfo=datetime.UTC)
    report.monitored_area_ha = 5000.0
    report.incidents_resolved = 12
    report.average_response_minutes = 45.0
    report.heat_spots_detected = 7
    report.vegetation_loss_estimated_ha = 120.5
    report.prevented_impact_estimate = "Estimativa de R$ 2M em danos evitados"
    report.ods = {"ods_13": True, "ods_15": True}
    report.created_at = datetime.datetime.now(datetime.UTC)
    return report


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_esg_requires_orgao(client):
    """GET /api/v1/esg without token — should return 401 or 403."""
    response = await client.get("/api/v1/esg")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_esg_not_found(client):
    """GET /api/v1/esg/{uuid} with orgao token, DB returns None → 404."""
    mock_db = AsyncMock()
    fake_orgao = make_fake_orgao()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_orgao

    not_found_result = MagicMock()
    not_found_result.scalar_one_or_none.return_value = None

    mock_db.execute.side_effect = [user_result, not_found_result]
    mock_db.commit = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        token = create_access_token(str(ORGAO_USER_ID), "orgao")
        response = await client.get(
            f"/api/v1/esg/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_esg_report(client):
    """POST /api/v1/esg with orgao token, DB mocked → 201 with expected fields."""
    mock_db = AsyncMock()
    fake_orgao = make_fake_orgao()
    fake_report = make_fake_esg_report()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_orgao
    mock_db.execute.return_value = user_result
    mock_db.commit = AsyncMock()

    def _inject_fields(obj):
        from app.esg.model import ESGReport

        if isinstance(obj, ESGReport):
            obj.id = fake_report.id
            obj.created_at = fake_report.created_at

    mock_db.add = MagicMock(side_effect=_inject_fields)
    mock_db.flush = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        token = create_access_token(str(ORGAO_USER_ID), "orgao")
        response = await client.post(
            "/api/v1/esg",
            json={
                "protected_area_id": str(AREA_ID),
                "period_start": "2025-01-01T00:00:00Z",
                "period_end": "2025-03-31T23:59:59Z",
                "monitored_area_ha": 5000.0,
                "incidents_resolved": 12,
                "average_response_minutes": 45.0,
                "heat_spots_detected": 7,
                "vegetation_loss_estimated_ha": 120.5,
                "prevented_impact_estimate": "Estimativa de R$ 2M em danos evitados",
                "ods": {"ods_13": True, "ods_15": True},
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["incidents_resolved"] == 12
        assert data["monitored_area_ha"] == 5000.0
        assert data["ods"] == {"ods_13": True, "ods_15": True}
    finally:
        app.dependency_overrides.clear()
