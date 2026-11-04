"""Tests for the Audit Log API and Admin Stats endpoint (Phase 10).

All tests use AsyncMock — no live PostgreSQL required.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

ADMIN_USER_ID = uuid.uuid4()
ORGAO_USER_ID = uuid.uuid4()


def make_fake_admin(role: str = "admin") -> MagicMock:
    user = MagicMock()
    user.id = ADMIN_USER_ID
    user.name = "Admin Test"
    user.email = "admin@test.com"
    user.role = role
    user.is_active = True
    user.session_version = 0
    user.must_change_password = False
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


# Listing, filters, sanitization and export run against PostGIS in
# tests/test_postgis_admin.py.


# ---------------------------------------------------------------------------
# Test 3: stats endpoint requires orgao role (no token → 401/403)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_requires_orgao(client):
    """GET /api/v1/admin/stats without token — should return 401 or 403."""
    response = await client.get("/api/v1/admin/stats")
    assert response.status_code in (401, 403)
