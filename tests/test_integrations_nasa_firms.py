"""Tests for NASA FIRMS orbital alerts endpoint and service."""

from unittest.mock import AsyncMock, patch

import pytest

from app.integrations.nasa_firms.service import _csv_row_to_alert, _parse_confidence

# ---------------------------------------------------------------------------
# Unit tests — parsing helpers
# ---------------------------------------------------------------------------


class TestParseConfidence:
    def test_named_low(self):
        assert _parse_confidence("low") == 25

    def test_named_nominal(self):
        assert _parse_confidence("nominal") == 60

    def test_named_high(self):
        assert _parse_confidence("high") == 90

    def test_integer_string(self):
        assert _parse_confidence("75") == 75

    def test_unknown_defaults_to_50(self):
        assert _parse_confidence("unknown") == 50

    def test_case_insensitive(self):
        assert _parse_confidence("HIGH") == 90
        assert _parse_confidence("Low") == 25


class TestCsvRowToAlert:
    def _valid_row(self) -> dict:
        return {
            "latitude": "-4.200",
            "longitude": "-38.500",
            "confidence": "high",
            "acq_date": "2026-05-31",
            "acq_time": "1230",
            "frp": "12.5",
            "satellite": "N",
        }

    def test_valid_row_returns_alert(self):
        alert = _csv_row_to_alert(self._valid_row())
        assert alert is not None
        assert alert.lat == pytest.approx(-4.2)
        assert alert.type == "heat_spot"
        assert alert.confidence == 90

    def test_low_confidence_returns_none(self):
        row = self._valid_row()
        row["confidence"] = "10"
        result = _csv_row_to_alert(row)
        assert result is None

    def test_missing_latitude_returns_none(self):
        row = self._valid_row()
        del row["latitude"]
        result = _csv_row_to_alert(row)
        assert result is None

    def test_invalid_date_returns_none(self):
        row = self._valid_row()
        row["acq_date"] = "not-a-date"
        result = _csv_row_to_alert(row)
        assert result is None


# ---------------------------------------------------------------------------
# Integration tests — HTTP endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orbital_alerts_list_returns_200(client):
    response = await client.get("/api/v1/orbital-alerts")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["source_status"] in {
        "live", "cached", "disabled_missing_api_key", "unavailable"
    }


@pytest.mark.asyncio
async def test_orbital_alerts_disabled_without_key(client):
    """Without NASA_FIRMS_MAP_KEY the endpoint must report disabled status."""
    from app.integrations._cache import cache_clear

    cache_clear()  # Ensure no cached result from a previous test

    response = await client.get("/api/v1/orbital-alerts")
    assert response.status_code == 200
    data = response.json()
    # In test env no providers are enabled — must report disabled
    assert data["source_status"] == "disabled_missing_api_key"
    # Demo alerts are still returned so the frontend has something to display
    assert data["total"] > 0


@pytest.mark.asyncio
async def test_ingest_disabled_without_key(client):
    """POST /ingest must return disabled_missing_api_key when no providers are enabled."""
    response = await client.post("/api/v1/orbital-alerts/ingest")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "disabled_missing_api_key"
    # Aggregator now covers both providers; message indicates configuration needed
    assert "ENABLED" in data["message"] or "habilitada" in data["message"].lower()


# ---------------------------------------------------------------------------
# Unit tests — v2 schema fields (backwards-compat)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orbital_alerts_response_has_v2_fields(client):
    """Response must include new optional fields for multi-source metadata."""
    response = await client.get("/api/v1/orbital-alerts")
    assert response.status_code == 200
    data = response.json()
    # Backwards-compat fields must be present (default to empty/false)
    assert "providers_attempted" in data
    assert "providers_successful" in data
    assert "fallback_used" in data
    assert "errors" in data
    assert isinstance(data["providers_attempted"], list)
    assert isinstance(data["providers_successful"], list)
    assert isinstance(data["errors"], list)
    assert isinstance(data["fallback_used"], bool)


@pytest.mark.asyncio
async def test_ingest_response_has_v2_fields(client):
    """IngestResponse must include new optional fields."""
    response = await client.post("/api/v1/orbital-alerts/ingest")
    assert response.status_code == 200
    data = response.json()
    assert "providers_successful" in data
    assert "fallback_used" in data
    assert "errors" in data


# ---------------------------------------------------------------------------
# Unit tests — NASA FIRMS service with mocked provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ingest_viirs_with_mocked_provider():
    """With mocked CSV rows, ingest_viirs must parse and cache alerts."""
    from app.integrations._cache import cache_clear
    from app.integrations.nasa_firms.service import ingest_viirs

    cache_clear()

    mock_rows = [
        {
            "latitude": "-4.200",
            "longitude": "-38.500",
            "confidence": "high",
            "acq_date": "2026-05-31",
            "acq_time": "1230",
            "frp": "12.5",
            "satellite": "N",
        },
        {
            "latitude": "-4.500",
            "longitude": "-39.100",
            "confidence": "nominal",
            "acq_date": "2026-05-31",
            "acq_time": "1400",
            "frp": "5.0",
            "satellite": "N",
        },
    ]

    with (
        patch("app.integrations.nasa_firms.service.settings") as mock_settings,
        patch(
            "app.integrations.nasa_firms.service.firms_client.fetch_viirs_csv",
            new_callable=AsyncMock,
            return_value=mock_rows,
        ),
    ):
        mock_settings.nasa_firms_map_key = "fake-key-for-test"
        mock_settings.nasa_firms_enabled = True
        mock_settings.fire_bbox = "-45.0,-12.0,-34.5,2.5"
        mock_settings.fire_lookback_days = 1
        mock_settings.external_api_cache_ttl_minutes = 60

        result = await ingest_viirs()

    assert result.status == "ok"
    assert result.records_fetched == 2
    assert result.records_inserted == 2
    assert result.records_skipped == 0
    assert "nasa_firms" in result.providers_successful
    assert result.fallback_used is False


@pytest.mark.asyncio
async def test_ingest_viirs_external_error_returns_fallback():
    """When the NASA FIRMS HTTP call fails, ingest_viirs must return error status."""
    import httpx

    from app.integrations._cache import cache_clear
    from app.integrations.nasa_firms.service import ingest_viirs

    cache_clear()

    with (
        patch("app.integrations.nasa_firms.service.settings") as mock_settings,
        patch(
            "app.integrations.nasa_firms.service.firms_client.fetch_viirs_csv",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectTimeout("timed out"),
        ),
    ):
        mock_settings.nasa_firms_map_key = "fake-key-for-test"
        mock_settings.nasa_firms_enabled = True
        mock_settings.fire_bbox = "-45.0,-12.0,-34.5,2.5"
        mock_settings.fire_lookback_days = 1
        mock_settings.external_api_cache_ttl_minutes = 60

        result = await ingest_viirs()

    assert result.status == "error"
    assert result.fallback_used is True
    assert len(result.errors) > 0
    # Key must NOT appear in errors
    assert "fake-key-for-test" not in str(result.errors)


@pytest.mark.asyncio
async def test_list_alerts_fallback_when_disabled():
    """list_alerts() must always return demo data when providers are disabled."""
    from app.integrations.nasa_firms.service import list_alerts

    result = list_alerts()
    assert result.source_status == "disabled_missing_api_key"
    assert result.total > 0
    assert result.fallback_used is True
