from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_action
from app.core.enums import UserRole
from app.core.rate_limit import rate_limit
from app.database import get_db
from app.dependencies import require_role
from app.integrations.nasa_firms.schemas import (
    IngestResponse,
    OrbitalAlertListResponse,
)
from app.integrations.nasa_firms.service import ingest_viirs, list_alerts

router = APIRouter(prefix="/api/v1/orbital-alerts", tags=["orbital-alerts"])


@router.get(
    "",
    dependencies=[Depends(rate_limit("orbital-alerts", limit=60, window_seconds=60))],
)
async def get_orbital_alerts() -> OrbitalAlertListResponse:
    """List orbital heat-spot alerts (satellite thermal anomalies, not confirmed fires).

    source_status:
    - `live` / `cached`: NASA FIRMS data fetched now / earlier (see `fetched_at`).
    - `demo`: fictitious items, only when ORBITAL_ALERTS_DEMO_MODE=true.
    - `disabled_missing_api_key`: NASA_FIRMS_MAP_KEY absent — empty list.
    - `unavailable`: NASA FIRMS failed — empty list.

    Alerts are never persisted in this version (`persisted=false`).
    """
    return await list_alerts()


@router.post("/ingest")
async def trigger_ingest(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.ADMIN)),
) -> IngestResponse:
    """Fetch NASA FIRMS VIIRS data into the in-memory cache (admin only).

    Does NOT write to the database: `records_inserted` is always 0 and
    `status` is `processed_not_persisted` on success.
    """
    result = await ingest_viirs()
    await log_action(
        db,
        "orbital_alerts.ingest_triggered",
        "OrbitalAlertIngest",
        "nasa_firms_viirs",
        actor_name=current_user.name,
        actor_id=current_user.id,
        metadata={
            "status": result.status,
            "records_fetched": result.records_fetched,
            "records_valid": result.records_valid,
            "records_inserted": result.records_inserted,
        },
    )
    await db.commit()
    return result
