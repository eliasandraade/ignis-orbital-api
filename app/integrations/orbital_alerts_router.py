from fastapi import APIRouter

from app.integrations.nasa_firms.schemas import (
    IngestResponse,
    OrbitalAlertListResponse,
)
from app.integrations.nasa_firms.service import ingest_viirs, list_alerts

router = APIRouter(prefix="/api/v1/orbital-alerts", tags=["orbital-alerts"])


@router.get("", response_model=OrbitalAlertListResponse)
async def get_orbital_alerts() -> OrbitalAlertListResponse:
    """List recent orbital heat-spot alerts.

    Returns demo data with source_status='disabled_missing_api_key' when
    NASA_FIRMS_MAP_KEY is not configured.  After the key is set and the
    orbital_alerts migration is applied, this endpoint will return live data
    from the database (updated every 3h by the ingest cron).
    """
    return list_alerts()


@router.post("/ingest", response_model=IngestResponse)
async def trigger_ingest() -> IngestResponse:
    """Trigger a NASA FIRMS VIIRS data ingestion run.

    Returns status='disabled_missing_api_key' when NASA_FIRMS_MAP_KEY is absent.
    This is not an error — it is the expected state before the key is configured.

    When the key is present, fetches CSV for the configured bbox and parses rows.
    Persistence to the orbital_alerts table will be activated after the migration
    is applied.
    """
    return await ingest_viirs()
