"""Contract of /api/v1/orbital-alerts that needs no database.

Sprint 0 tested the live NASA read path here; since Sprint 1.3 the public
read comes only from PostGIS (tests/test_postgis_read_api.py). What stays
here: authorization of the administrative routes, filter validation and the
guarantee that a public read never reaches NASA or INPE.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.database import get_db
from app.dependencies import get_current_user
from app.main import app
from app.orbital import queries
from app.orbital.read_schemas import DetectionPage


def _user(role: str) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.role = role
    user.name = f"Usuário {role}"
    user.is_active = True
    return user


@pytest.fixture
def as_role():
    """Authenticate as a user with the given role; returns the mocked DB session."""
    session = AsyncMock()
    session.add = MagicMock()

    async def _db():
        yield session

    def _set(role: str):
        app.dependency_overrides[get_current_user] = lambda: _user(role)
        app.dependency_overrides[get_db] = _db
        return session

    return _set


# --- administrative routes -----------------------------------------------------------


async def test_ingest_requires_authentication(client):
    response = await client.post("/api/v1/orbital-alerts/ingest")
    assert response.status_code in (401, 403)


@pytest.mark.parametrize("role", ["publico", "campo", "gestor", "orgao"])
async def test_ingest_forbidden_below_admin(client, as_role, role):
    as_role(role)
    response = await client.post("/api/v1/orbital-alerts/ingest")
    assert response.status_code == 403


@pytest.mark.parametrize("path", ["/ingestion-runs", f"/ingestion-runs/{uuid.uuid4()}"])
async def test_ingestion_runs_are_admin_only(client, as_role, path):
    assert (await client.get(f"/api/v1/orbital-alerts{path}")).status_code in (401, 403)
    as_role("gestor")
    assert (await client.get(f"/api/v1/orbital-alerts{path}")).status_code == 403


# --- public read: database only ------------------------------------------------------


async def test_public_read_never_calls_providers_nor_starts_ingestion(client, monkeypatch):
    from app.integrations import orbital_alerts_router as router

    def _forbidden(*args, **kwargs):
        raise AssertionError("leitura pública não pode iniciar ingestão nem chamar provedor")

    async def _no_network(self, request):
        raise AssertionError(f"leitura pública tentou acessar a rede: {request.url.host}")

    async def _page(session, f, *, page, size, stale_after):
        return DetectionPage(
            items=[],
            total=0,
            page=page,
            size=size,
            pages=1,
            truncated=False,
            filters=f.applied(),
            sources=[],
        )

    monkeypatch.setattr(router, "IngestionRound", _forbidden)
    monkeypatch.setattr(router, "providers_from_settings", _forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _no_network)
    monkeypatch.setattr(queries, "list_detections", AsyncMock(side_effect=_page))
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    response = await client.get("/api/v1/orbital-alerts")
    assert response.status_code == 200
    assert response.json()["data_origin"] == "postgis"
    assert queries.list_detections.await_count == 1


@pytest.mark.parametrize(
    "query",
    [
        "from=2026-11-04T00:00:00Z&to=2026-11-01T00:00:00Z",  # inverted
        "from=2026-01-01T00:00:00Z&to=2026-11-01T00:00:00Z",  # > 92 days
        "source=DEMO",
        "jurisdiction=2304",  # not a 7-digit IBGE code
        "satellite=N20;DROP",
        "bbox=-41,-8,-37",  # 3 numbers
        "bbox=-80,-40,-30,10",  # wider than 20 degrees
        "bbox=-37,-8,-41,-3",  # west > east
        "bbox=-41,-8,nan,-3",
        "size=5001",
        "page=0",
    ],
)
async def test_invalid_filters_are_rejected_before_any_query(client, query, monkeypatch):
    called = AsyncMock()
    monkeypatch.setattr(queries, "list_detections", called)
    app.dependency_overrides[get_db] = lambda: AsyncMock()
    response = await client.get(f"/api/v1/orbital-alerts?{query}")
    assert response.status_code == 422
    called.assert_not_awaited()


def test_default_window_is_the_last_seven_days():
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 11, 4, 12, tzinfo=UTC)
    f = queries.build_filters(
        observed_from=None,
        observed_to=None,
        source=None,
        satellite=None,
        jurisdiction=None,
        bbox=None,
        now=now,
    )
    assert (f.observed_from, f.observed_to) == (now - timedelta(days=7), now)


def test_naive_datetimes_are_read_as_utc():
    from datetime import UTC, datetime

    f = queries.build_filters(
        observed_from=datetime(2026, 11, 1),
        observed_to=datetime(2026, 11, 2),
        source="INPE_QUEIMADAS",
        satellite="NOAA-20",
        jurisdiction="2304400",
        bbox="-41.5,-7.9,-37.2,-2.7",
    )
    assert f.observed_from.tzinfo is UTC
    assert f.bbox == (-41.5, -7.9, -37.2, -2.7)


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        (["disabled", "disabled"], "disabled"),
        (["never_ingested"], "never_ingested"),
        (["disabled", "never_ingested"], "never_ingested"),
        (["live", "live"], "live"),
        (["live", "unavailable"], "degraded"),
        (["live", "disabled"], "live"),
        (["stale", "stale"], "stale"),
        (["stale", "unavailable"], "unavailable"),
        (["unavailable"], "unavailable"),
    ],
)
def test_source_state_aggregation(states, expected):
    assert queries._source_state(states) == expected


def test_product_state_separates_failure_age_and_configuration():
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 11, 4, 12, tzinfo=UTC)
    hour = timedelta(hours=1)
    assert queries._product_state(None, None, now, hour) == "never_ingested"
    assert queries._product_state("disabled", None, now, hour) == "disabled"
    assert queries._product_state("unavailable", now, now, hour) == "unavailable"
    assert queries._product_state("partial", now, now, hour) == "unavailable"
    assert queries._product_state("ok", now - timedelta(minutes=5), now, hour) == "live"
    assert queries._product_state("ok", now - 2 * hour, now, hour) == "stale"
