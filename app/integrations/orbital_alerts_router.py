from fastapi import APIRouter

from app.integrations.nasa_firms.schemas import (
    IngestResponse,
    OrbitalAlertListResponse,
)
from app.integrations.orbital_alerts_service import get_aggregated_alerts, ingest_all_sources

router = APIRouter(prefix="/api/v1/orbital-alerts", tags=["orbital-alerts"])


@router.get("", response_model=OrbitalAlertListResponse)
async def get_orbital_alerts() -> OrbitalAlertListResponse:
    """List recent orbital heat-spot alerts aggregated from all enabled sources.

    Sources (each opt-in via env var):
    - NASA FIRMS VIIRS — requires NASA_FIRMS_MAP_KEY + NASA_FIRMS_ENABLED=true
    - INPE TerraBrasilis WFS — requires INPE_QUEIMADAS_ENABLED=true (free/public)

    Always returns a successful response; provider errors are captured in the
    `errors` field.  Demo data is returned when no providers are enabled so
    the frontend always has content to display.
    """
    return await get_aggregated_alerts()


@router.post("/ingest", response_model=IngestResponse)
async def trigger_ingest() -> IngestResponse:
    """Trigger a data ingestion run for all enabled fire-spot providers.

    Fetches fresh data from NASA FIRMS and/or INPE TerraBrasilis depending on
    which providers are enabled.  Returns a summary with per-provider status.

    Returns status='disabled_missing_api_key' when no providers are enabled —
    this is expected in the default configuration and is not an error.
    """
    return await ingest_all_sources()
