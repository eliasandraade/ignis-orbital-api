"""Honest-state contract for GET /api/v1/orbital-alerts and POST /ingest.

Regression tests for the Sprint 0 findings:
- demo alerts were reported as source_status="live" when a key was present;
- records_inserted reported rows that were never written to the database;
- ingest was callable without authentication;
- upstream error messages could embed the NASA MAP_KEY (it is part of the URL).
"""

import csv
import io
import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.database import get_db
from app.dependencies import get_current_user
from app.integrations.nasa_firms import service as firms_service
from app.integrations.nasa_firms.client import InvalidFirmsResponseError, MissingApiKeyError
from app.integrations.nasa_firms.service import _csv_row_to_alert
from app.main import app

FAKE_KEY = "FAKEMAPKEY0123456789"

CSV_OK = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
    "instrument,confidence,version,bright_ti5,frp,daynight\n"
    "-4.20000,-38.50000,330.1,0.4,0.4,2026-11-02,1530,N,VIIRS,n,2.0NRT,295.0,5.1,D\n"
    "-5.10000,-39.20000,340.5,0.4,0.4,2026-11-02,1530,N,VIIRS,h,2.0NRT,296.0,9.8,D\n"
    # duplicated row — must be deduplicated
    "-5.10000,-39.20000,340.5,0.4,0.4,2026-11-02,1530,N,VIIRS,h,2.0NRT,296.0,9.8,D\n"
    # low confidence — skipped
    "-6.00000,-40.00000,300.0,0.4,0.4,2026-11-02,1530,N,VIIRS,10,2.0NRT,290.0,1.0,D\n"
)


def _rows(csv_text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(csv_text)))


def _user(role: str) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.name = f"Test {role}"
    user.role = role
    user.is_active = True
    return user


def _http_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", f"https://firms.example/api/area/csv/{FAKE_KEY}/VIIRS")
    return httpx.HTTPStatusError(
        f"Error for url {request.url}",
        request=request,
        response=httpx.Response(status, request=request),
    )


@pytest.fixture
def firms_key(monkeypatch):
    monkeypatch.setattr(firms_service.settings, "nasa_firms_map_key", FAKE_KEY)
    return FAKE_KEY


@pytest.fixture
def demo_mode(monkeypatch):
    monkeypatch.setattr(firms_service.settings, "orbital_alerts_demo_mode", True)


@pytest.fixture
def fake_firms(monkeypatch):
    """Replace the network call; records how many times NASA was called."""
    state = {"calls": 0, "rows": None, "exc": None}

    async def _fetch(bbox, date=None):
        state["calls"] += 1
        if state["exc"] is not None:
            raise state["exc"]
        return state["rows"] if state["rows"] is not None else _rows(CSV_OK)

    monkeypatch.setattr(firms_service.firms_client, "fetch_viirs_csv", _fetch)
    return state


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


@pytest.fixture
def mock_transport(monkeypatch):
    """Route the FIRMS client's httpx calls to a canned response."""
    real_client = httpx.AsyncClient

    def _install(response: httpx.Response):
        def _factory(**kwargs):
            return real_client(transport=httpx.MockTransport(lambda req: response), **kwargs)

        monkeypatch.setattr(firms_service.firms_client.httpx, "AsyncClient", _factory)

    return _install


# --- GET without key ------------------------------------------------------------


async def test_list_without_key_returns_no_data_and_never_live(client):
    data = (await client.get("/api/v1/orbital-alerts")).json()
    assert data["source_status"] == "disabled_missing_api_key"
    assert data["items"] == []
    assert data["total"] == 0
    assert data["data_origin"] == "none"
    assert data["persisted"] is False
    assert "NASA_FIRMS_MAP_KEY" in data["message"]


async def test_list_demo_mode_is_explicitly_flagged(client, demo_mode):
    data = (await client.get("/api/v1/orbital-alerts")).json()
    assert data["source_status"] == "demo"
    assert data["data_origin"] == "demo"
    assert data["total"] == len(data["items"]) > 0
    assert all(item["is_demo"] for item in data["items"])
    assert all(not item["source"].startswith("NASA") for item in data["items"])


async def test_list_with_key_never_returns_demo_items(client, firms_key, demo_mode, fake_firms):
    data = (await client.get("/api/v1/orbital-alerts")).json()
    assert data["source_status"] == "live"
    assert not any(item["is_demo"] for item in data["items"])
    assert not any(item["id"].startswith("demo-") for item in data["items"])


# --- GET with key -----------------------------------------------------------------


async def test_list_with_key_live_then_cached(client, firms_key, fake_firms):
    first = (await client.get("/api/v1/orbital-alerts")).json()
    assert first["source_status"] == "live"
    assert first["data_origin"] == "nasa_firms"
    assert first["persisted"] is False
    assert first["total"] == 2  # 4 rows: 1 duplicate + 1 low confidence removed
    assert first["fetched_at"] is not None
    assert "não confirmam incêndio" in first["disclaimer"].lower()

    second = (await client.get("/api/v1/orbital-alerts")).json()
    assert second["source_status"] == "cached"
    assert second["cached_at"] == first["fetched_at"]
    assert [i["id"] for i in second["items"]] == [i["id"] for i in first["items"]]
    assert fake_firms["calls"] == 1


async def test_list_with_key_and_zero_detections_is_live_and_empty(client, firms_key, fake_firms):
    fake_firms["rows"] = []
    data = (await client.get("/api/v1/orbital-alerts")).json()
    assert data["source_status"] == "live"
    assert data["total"] == 0


async def test_list_upstream_failure_is_unavailable_without_leaking_key(
    client, firms_key, fake_firms
):
    fake_firms["exc"] = _http_error(500)

    resp = await client.get("/api/v1/orbital-alerts")
    data = resp.json()
    assert data["source_status"] == "unavailable"
    assert data["items"] == []
    assert data["data_origin"] == "none"
    assert FAKE_KEY not in resp.text
    assert "HTTPStatusError" in data["message"]

    # Within the backoff window NASA is not called again.
    again = (await client.get("/api/v1/orbital-alerts")).json()
    assert again["source_status"] == "unavailable"
    assert fake_firms["calls"] == 1


async def test_list_timeout_is_unavailable(client, firms_key, fake_firms):
    fake_firms["exc"] = httpx.ConnectTimeout("timed out")
    data = (await client.get("/api/v1/orbital-alerts")).json()
    assert data["source_status"] == "unavailable"
    assert "ConnectTimeout" in data["message"]


async def test_list_invalid_firms_body_is_unavailable(client, firms_key, mock_transport):
    mock_transport(httpx.Response(200, text="Invalid MAP_KEY."))
    data = (await client.get("/api/v1/orbital-alerts")).json()
    assert data["source_status"] == "unavailable"
    assert data["total"] == 0


# --- client ---------------------------------------------------------------------


async def test_client_rejects_non_csv_body(firms_key, mock_transport):
    mock_transport(httpx.Response(200, text="Invalid MAP_KEY."))
    with pytest.raises(InvalidFirmsResponseError):
        await firms_service.firms_client.fetch_viirs_csv("-45,-12,-34.5,2.5")


async def test_client_parses_valid_csv(firms_key, mock_transport):
    mock_transport(httpx.Response(200, text=CSV_OK))
    rows = await firms_service.firms_client.fetch_viirs_csv("-45,-12,-34.5,2.5")
    assert len(rows) == 4


async def test_client_without_key_makes_no_network_call():
    with pytest.raises(MissingApiKeyError):
        await firms_service.firms_client.fetch_viirs_csv("-45,-12,-34.5,2.5")


# --- POST /ingest authorization ----------------------------------------------------


async def test_ingest_requires_authentication(client):
    response = await client.post("/api/v1/orbital-alerts/ingest")
    assert response.status_code in (401, 403)


@pytest.mark.parametrize("role", ["publico", "campo", "gestor", "orgao"])
async def test_ingest_forbidden_below_admin(client, as_role, role):
    as_role(role)
    response = await client.post("/api/v1/orbital-alerts/ingest")
    assert response.status_code == 403


# --- POST /ingest results ----------------------------------------------------------


async def test_ingest_without_key_reports_disabled_and_audits(client, as_role):
    session = as_role("admin")
    data = (await client.post("/api/v1/orbital-alerts/ingest")).json()
    assert data["status"] == "disabled_missing_api_key"
    assert data["records_inserted"] == 0
    assert data["persisted"] is False
    audit = session.add.call_args.args[0]
    assert audit.action == "orbital_alerts.ingest_triggered"
    assert audit.metadata_json["status"] == "disabled_missing_api_key"
    session.commit.assert_awaited()


async def test_ingest_never_claims_persistence(client, as_role, firms_key, fake_firms):
    as_role("admin")
    data = (await client.post("/api/v1/orbital-alerts/ingest")).json()
    assert data["status"] == "processed_not_persisted"
    assert data["records_fetched"] == 4
    assert data["records_valid"] == 2
    assert data["records_inserted"] == 0
    assert data["records_skipped"] == 2
    assert data["persisted"] is False
    assert "Nenhum registro foi gravado" in data["message"]


async def test_ingest_refreshes_cache_for_list(client, as_role, firms_key, fake_firms):
    as_role("admin")
    await client.post("/api/v1/orbital-alerts/ingest")
    data = (await client.get("/api/v1/orbital-alerts")).json()
    assert data["source_status"] == "cached"
    assert fake_firms["calls"] == 1


async def test_ingest_upstream_failure_is_unavailable_without_leaking_key(
    client, as_role, firms_key, fake_firms
):
    as_role("admin")
    fake_firms["exc"] = _http_error(403)
    response = await client.post("/api/v1/orbital-alerts/ingest")
    data = response.json()
    assert data["status"] == "unavailable"
    assert data["records_inserted"] == 0
    assert FAKE_KEY not in response.text


# --- parsing ---------------------------------------------------------------------


def test_alert_ids_are_stable_across_fetches():
    row = _rows(CSV_OK)[0]
    assert _csv_row_to_alert(row).id == _csv_row_to_alert(dict(row)).id


def test_out_of_range_coordinates_are_rejected():
    row = _rows(CSV_OK)[0]
    row["latitude"] = "123.0"
    assert _csv_row_to_alert(row) is None
