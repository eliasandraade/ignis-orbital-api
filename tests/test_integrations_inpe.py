"""Tests for INPE TerraBrasilis orbital alerts integration."""

from unittest.mock import AsyncMock, patch

import pytest

from app.integrations.inpe_queimadas.schemas import InpeFocus  # noqa: F401 — used in tests
from app.integrations.inpe_queimadas.service import fetch_inpe_alerts

# ---------------------------------------------------------------------------
# Unit tests — GeoJSON parser
# ---------------------------------------------------------------------------


def _make_geojson(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def _make_feature(
    inpe_id: int = 12345,
    lat: float = -4.2,
    lng: float = -38.5,
    viewed_at: str = "2026-06-01T00:15:00-03:00",
    satelite: str = "AQUA_M-T",
    municipio: str = "Fortaleza",
    biome: str = "Caatinga",
) -> dict:
    return {
        "type": "Feature",
        "id": f"active-fire-today.fid-test-{inpe_id}",
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
        "geometry_name": "geom",
        "properties": {
            "id": inpe_id,
            "view_date": "2026-06-01",
            "viewed_at": viewed_at,
            "satelite": satelite,
            "municipio": municipio,
            "biome": biome,
        },
    }


# ---------------------------------------------------------------------------
# Unit tests — service layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_inpe_alerts_disabled_returns_empty():
    """When INPE_QUEIMADAS_ENABLED=false, service returns empty list without HTTP call."""
    with patch("app.integrations.inpe_queimadas.service.settings") as mock_settings:
        mock_settings.inpe_queimadas_enabled = False
        mock_settings.fire_bbox = "-45.0,-12.0,-34.5,2.5"
        mock_settings.external_api_cache_ttl_minutes = 60

        alerts, error = await fetch_inpe_alerts()

    assert alerts == []
    assert error is None  # disabled is NOT an error


@pytest.mark.asyncio
async def test_fetch_inpe_alerts_with_mocked_response():
    """With mocked GeoJSON, service must normalize to OrbitalAlert correctly."""
    from app.integrations._cache import cache_clear

    cache_clear()

    mock_focuses = [
        InpeFocus(
            feature_id="active-fire-today.fid-test-001",
            inpe_id=838830,
            lat=-4.2,
            lng=-38.5,
            view_date="2026-06-01",
            viewed_at=None,
            satelite="AQUA_M-T",
            municipio="Fortaleza",
            biome="Caatinga",
        )
    ]

    with (
        patch("app.integrations.inpe_queimadas.service.settings") as mock_settings,
        patch(
            "app.integrations.inpe_queimadas.service.fetch_active_fires",
            new_callable=AsyncMock,
            return_value=mock_focuses,
        ),
    ):
        mock_settings.inpe_queimadas_enabled = True
        mock_settings.fire_bbox = "-45.0,-12.0,-34.5,2.5"
        mock_settings.external_api_cache_ttl_minutes = 60

        alerts, error = await fetch_inpe_alerts(force_refresh=True)

    assert error is None
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert.id == "INPE-838830"
    assert alert.source == "INPE_TERRABRASILIS"
    assert alert.type == "heat_spot"
    assert alert.lat == pytest.approx(-4.2)
    assert alert.lng == pytest.approx(-38.5)
    assert alert.confidence == 70
    assert alert.raw_data is not None
    assert alert.raw_data["biome"] == "Caatinga"


@pytest.mark.asyncio
async def test_fetch_inpe_alerts_http_error_returns_fallback():
    """When the INPE HTTP call fails, service must return empty list + error message."""
    import httpx

    from app.integrations._cache import cache_clear

    cache_clear()

    with (
        patch("app.integrations.inpe_queimadas.service.settings") as mock_settings,
        patch(
            "app.integrations.inpe_queimadas.service.fetch_active_fires",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectTimeout("timed out"),
        ),
    ):
        mock_settings.inpe_queimadas_enabled = True
        mock_settings.fire_bbox = "-45.0,-12.0,-34.5,2.5"
        mock_settings.external_api_cache_ttl_minutes = 60

        alerts, error = await fetch_inpe_alerts(force_refresh=True)

    assert alerts == []
    assert error is not None
    assert "INPE" in error
    # No secrets in error (INPE is keyless so trivially true, but good habit)
    assert len(error) < 200


# ---------------------------------------------------------------------------
# Integration tests — HTTP endpoint (aggregated, INPE + NASA both disabled)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orbital_alerts_no_providers_returns_demo(client):
    """With no providers enabled, endpoint returns demo data with disabled status."""
    from app.integrations._cache import cache_clear

    cache_clear()

    response = await client.get("/api/v1/orbital-alerts")
    assert response.status_code == 200
    data = response.json()

    assert data["source_status"] == "disabled_missing_api_key"
    assert data["total"] > 0  # demo data always present
    assert data["fallback_used"] is True
    assert data["providers_attempted"] == []
    assert data["providers_successful"] == []


@pytest.mark.asyncio
async def test_orbital_alerts_contract_preserved(client):
    """Existing frontend contract fields must always be present."""
    response = await client.get("/api/v1/orbital-alerts")
    assert response.status_code == 200
    data = response.json()

    # Core contract fields (pre-existing, must never disappear)
    assert "items" in data
    assert "total" in data
    assert "source_status" in data
    # New optional fields
    assert "providers_attempted" in data
    assert "providers_successful" in data
    assert "fallback_used" in data
    assert "errors" in data

    # All items must match OrbitalAlert shape
    for item in data["items"]:
        assert "id" in item
        assert "type" in item
        assert "lat" in item
        assert "lng" in item
        assert "confidence" in item
        assert "source" in item
        assert "detected_at" in item
        assert "fetched_at" in item


@pytest.mark.asyncio
async def test_ingest_all_no_providers_returns_disabled(client):
    """POST /ingest with no providers enabled returns disabled, not error."""
    response = await client.post("/api/v1/orbital-alerts/ingest")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "disabled_missing_api_key"
    assert data["fallback_used"] is True
    assert data["providers_successful"] == []
