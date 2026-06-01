"""Tests for Open-Meteo weather risk endpoint and service."""

from unittest.mock import AsyncMock, patch

import pytest

from app.integrations._cache import cache_clear
from app.integrations.open_meteo.service import _calculate_risk


@pytest.fixture(autouse=True)
def clear_cache():
    cache_clear()
    yield
    cache_clear()


# ---------------------------------------------------------------------------
# Unit tests — risk calculation algorithm
# ---------------------------------------------------------------------------


class TestCalculateRisk:
    def test_low_risk_mild_conditions(self):
        score, level, factors, recommendation = _calculate_risk(
            temp=22.0, humidity=70.0, wind_speed=8.0, precipitation=5.0
        )
        assert level == "low"
        assert score <= 25

    def test_high_temp_increases_score(self):
        score_high, *_ = _calculate_risk(
            temp=42.0, humidity=60.0, wind_speed=10.0, precipitation=0.0
        )
        score_low, *_ = _calculate_risk(
            temp=20.0, humidity=60.0, wind_speed=10.0, precipitation=0.0
        )
        assert score_high > score_low

    def test_low_humidity_increases_score(self):
        score_dry, *_ = _calculate_risk(
            temp=30.0, humidity=15.0, wind_speed=10.0, precipitation=0.0
        )
        score_humid, *_ = _calculate_risk(
            temp=30.0, humidity=80.0, wind_speed=10.0, precipitation=0.0
        )
        assert score_dry > score_humid

    def test_high_wind_increases_score(self):
        score_windy, *_ = _calculate_risk(
            temp=30.0, humidity=50.0, wind_speed=60.0, precipitation=0.0
        )
        score_calm, *_ = _calculate_risk(
            temp=30.0, humidity=50.0, wind_speed=5.0, precipitation=0.0
        )
        assert score_windy > score_calm

    def test_heavy_rain_reduces_score(self):
        score_wet, *_ = _calculate_risk(
            temp=40.0, humidity=20.0, wind_speed=50.0, precipitation=20.0
        )
        score_dry, *_ = _calculate_risk(
            temp=40.0, humidity=20.0, wind_speed=50.0, precipitation=0.0
        )
        assert score_wet < score_dry

    def test_critical_conditions_score_above_75(self):
        score, level, _, _ = _calculate_risk(
            temp=42.0, humidity=15.0, wind_speed=55.0, precipitation=0.0
        )
        assert level == "critical"
        assert score > 75

    def test_score_never_below_zero(self):
        score, *_ = _calculate_risk(temp=10.0, humidity=90.0, wind_speed=2.0, precipitation=100.0)
        assert score >= 0

    def test_score_never_above_100(self):
        score, *_ = _calculate_risk(temp=50.0, humidity=5.0, wind_speed=100.0, precipitation=0.0)
        assert score <= 100

    def test_none_values_handled_gracefully(self):
        score, level, factors, recommendation = _calculate_risk(
            temp=None, humidity=None, wind_speed=None, precipitation=None
        )
        assert isinstance(score, int)
        assert level in {"low", "moderate", "high", "critical"}

    def test_factors_list_is_not_empty_for_extreme_conditions(self):
        _, _, factors, _ = _calculate_risk(
            temp=42.0, humidity=15.0, wind_speed=55.0, precipitation=0.0
        )
        assert len(factors) > 0


# ---------------------------------------------------------------------------
# Integration tests — HTTP endpoint
# ---------------------------------------------------------------------------


_MOCK_OM_RESPONSE = {
    "current": {
        "temperature_2m": 35.0,
        "relative_humidity_2m": 30.0,
        "wind_speed_10m": 25.0,
        "wind_direction_10m": 90.0,
        "precipitation": 0.0,
    }
}


@pytest.mark.asyncio
async def test_weather_risk_endpoint_live(client):
    with patch(
        "app.integrations.open_meteo.client.fetch_current_weather",
        new_callable=AsyncMock,
        return_value=_MOCK_OM_RESPONSE,
    ):
        response = await client.get("/api/v1/environment/weather-risk?lat=-4.005&lng=-39.460")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "Open-Meteo"
    assert data["source_status"] == "live"
    assert data["latitude"] == pytest.approx(-4.005)
    assert data["longitude"] == pytest.approx(-39.460)
    assert isinstance(data["risk_score"], int)
    assert data["risk_level"] in {"low", "moderate", "high", "critical"}
    assert isinstance(data["factors"], list)
    assert "recommendation" in data


@pytest.mark.asyncio
async def test_weather_risk_endpoint_cached(client):
    with patch(
        "app.integrations.open_meteo.client.fetch_current_weather",
        new_callable=AsyncMock,
        return_value=_MOCK_OM_RESPONSE,
    ) as mock_fetch:
        await client.get("/api/v1/environment/weather-risk?lat=-4.005&lng=-39.460")
        response = await client.get("/api/v1/environment/weather-risk?lat=-4.005&lng=-39.460")

    # Second call should be from cache — external API called only once
    assert mock_fetch.call_count == 1
    data = response.json()
    assert data["source_status"] == "cached"


@pytest.mark.asyncio
async def test_weather_risk_endpoint_unavailable(client):
    with patch(
        "app.integrations.open_meteo.client.fetch_current_weather",
        new_callable=AsyncMock,
        side_effect=Exception("Connection refused"),
    ):
        response = await client.get("/api/v1/environment/weather-risk?lat=-4.005&lng=-39.460")

    assert response.status_code == 200
    data = response.json()
    assert data["source_status"] == "unavailable"


@pytest.mark.asyncio
async def test_weather_risk_invalid_coords(client):
    response = await client.get("/api/v1/environment/weather-risk?lat=999&lng=-39.460")
    assert response.status_code == 422
