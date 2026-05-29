"""Tests for the Audit Log API and Admin Stats endpoint (Phase 10).

All tests use AsyncMock — no live PostgreSQL required.
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


# ---------------------------------------------------------------------------
# Test 1: audit-logs endpoint requires admin role (no token → 401/403)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_requires_admin(client):
    """GET /api/v1/admin/audit-logs without token — should return 401 or 403."""
    response = await client.get("/api/v1/admin/audit-logs")
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Test 2: audit-logs with admin token returns paginated result
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_admin_audit_list():
    """Mock DB: admin user lookup succeeds; audit list returns empty page."""
    mock_db = AsyncMock()
    fake_admin = make_fake_admin()

    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = fake_admin

    call_count = 0

    def side_effect(query):
        nonlocal call_count
        call_count += 1
        mr = MagicMock()
        if call_count == 1:
            # First call: auth user lookup
            mr.scalar_one_or_none.return_value = fake_admin
        elif call_count == 2:
            # Second call: count query
            mr.scalar_one.return_value = 0
        else:
            # Third call: list query
            mr.scalars.return_value.all.return_value = []
        return mr

    mock_db.execute = AsyncMock(side_effect=side_effect)
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    yield mock_db
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_audit_list(client, db_admin_audit_list):
    """GET /api/v1/admin/audit-logs with admin token, mocked DB — 200 with Page."""
    token = create_access_token(str(ADMIN_USER_ID), "admin")
    response = await client.get(
        "/api/v1/admin/audit-logs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "size" in data
    assert "pages" in data
    assert data["items"] == []
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# Test 3: stats endpoint requires orgao role (no token → 401/403)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_requires_orgao(client):
    """GET /api/v1/admin/stats without token — should return 401 or 403."""
    response = await client.get("/api/v1/admin/stats")
    assert response.status_code in (401, 403)
