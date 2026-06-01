"""Tests for NASA FIRMS orbital alerts endpoint and service."""

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
    response = await client.get("/api/v1/orbital-alerts")
    assert response.status_code == 200
    data = response.json()
    # In test env the key is empty — must report disabled
    assert data["source_status"] == "disabled_missing_api_key"
    # Demo alerts are still returned so the frontend has something to display
    assert data["total"] > 0


@pytest.mark.asyncio
async def test_ingest_disabled_without_key(client):
    """POST /ingest must return disabled status clearly when key is absent."""
    response = await client.post("/api/v1/orbital-alerts/ingest")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "disabled_missing_api_key"
    assert "NASA_FIRMS_MAP_KEY" in data["message"]
