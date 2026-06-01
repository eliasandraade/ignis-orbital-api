"""Tests for OpenStreetMap/Nominatim reverse geocoding endpoint and service."""

from unittest.mock import AsyncMock, patch

import pytest

from app.integrations._cache import cache_clear
from app.integrations.openstreetmap.service import _extract_address_field, _round_coord


@pytest.fixture(autouse=True)
def clear_cache():
    cache_clear()
    yield
    cache_clear()


# ---------------------------------------------------------------------------
# Unit tests — helper functions
# ---------------------------------------------------------------------------


class TestRoundCoord:
    def test_rounds_to_3_decimals(self):
        assert _round_coord(-4.12345) == -4.123
        assert _round_coord(-38.9999) == -39.0

    def test_positive_coord(self):
        assert _round_coord(45.6789) == pytest.approx(45.679)


class TestExtractAddressField:
    def test_returns_first_matching_key(self):
        address = {"city": "Fortaleza", "state": "Ceará"}
        assert _extract_address_field(address, "city", "town") == "Fortaleza"

    def test_falls_through_to_second_key(self):
        address = {"town": "Maranguape", "state": "Ceará"}
        assert _extract_address_field(address, "city", "town") == "Maranguape"

    def test_returns_none_when_no_key_matches(self):
        address = {"state": "Ceará"}
        assert _extract_address_field(address, "city", "town") is None


# ---------------------------------------------------------------------------
# Integration tests — HTTP endpoint
# ---------------------------------------------------------------------------


_MOCK_NOMINATIM_RESPONSE = {
    "display_name": "Maranguape, Ceará, Brasil",
    "address": {
        "city": "Maranguape",
        "state": "Ceará",
        "country": "Brasil",
        "country_code": "br",
    },
}


@pytest.mark.asyncio
async def test_reverse_geocoding_live(client):
    with patch(
        "app.integrations.openstreetmap.client.fetch_reverse_geocoding",
        new_callable=AsyncMock,
        return_value=_MOCK_NOMINATIM_RESPONSE,
    ):
        response = await client.get("/api/v1/geocoding/reverse?lat=-4.005&lng=-39.460")

    assert response.status_code == 200
    data = response.json()
    assert data["source"] == "OpenStreetMap/Nominatim"
    assert data["latitude"] == pytest.approx(-4.005)
    assert data["municipality"] == "Maranguape"
    assert data["state"] == "Ceará"
    assert data["country"] == "Brasil"
    assert data["cached"] is False


@pytest.mark.asyncio
async def test_reverse_geocoding_cached(client):
    with patch(
        "app.integrations.openstreetmap.client.fetch_reverse_geocoding",
        new_callable=AsyncMock,
        return_value=_MOCK_NOMINATIM_RESPONSE,
    ) as mock_fetch:
        await client.get("/api/v1/geocoding/reverse?lat=-4.005&lng=-39.460")
        response = await client.get("/api/v1/geocoding/reverse?lat=-4.005&lng=-39.460")

    # Nominatim should only be called once — second response from cache
    assert mock_fetch.call_count == 1
    data = response.json()
    assert data["cached"] is True


@pytest.mark.asyncio
async def test_reverse_geocoding_nominatim_unavailable(client):
    with patch(
        "app.integrations.openstreetmap.client.fetch_reverse_geocoding",
        new_callable=AsyncMock,
        side_effect=Exception("Connection timeout"),
    ):
        response = await client.get("/api/v1/geocoding/reverse?lat=-4.005&lng=-39.460")

    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] is None
    assert data["municipality"] is None
    assert data["cached"] is False


@pytest.mark.asyncio
async def test_reverse_geocoding_invalid_lat(client):
    response = await client.get("/api/v1/geocoding/reverse?lat=200&lng=-39.460")
    assert response.status_code == 422
