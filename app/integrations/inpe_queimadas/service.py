"""INPE Queimadas service layer.

Fetches active fire spots from INPE TerraBrasilis WFS and normalizes
them to the shared OrbitalAlert schema used throughout the platform.

When INPE_QUEIMADAS_ENABLED=false (default), fetch_inpe_alerts() returns
an empty list without making any network call.  This makes the feature
safely opt-in — no production impact until explicitly enabled.

Cache strategy: same TTL as other integrations (EXTERNAL_API_CACHE_TTL_MINUTES).
In-memory per-process — see _cache.py note on multi-worker limitation.
"""

import logging
from datetime import UTC, datetime

import httpx

from app.config import get_settings
from app.integrations._cache import cache_get, cache_set
from app.integrations.inpe_queimadas.client import fetch_active_fires
from app.integrations.nasa_firms.schemas import OrbitalAlert

logger = logging.getLogger(__name__)
settings = get_settings()

_CACHE_KEY = "inpe_queimadas:alerts"
_DEFAULT_CONFIDENCE = 70  # active-fire-today data is confirmed by INPE satellite network


def _to_orbital_alert(focus) -> OrbitalAlert:  # type: ignore[no-untyped-def]
    detected_at = focus.viewed_at or datetime.now(UTC)
    # Ensure timezone-aware datetime
    if detected_at.tzinfo is None:
        detected_at = detected_at.replace(tzinfo=UTC)

    return OrbitalAlert(
        id=f"INPE-{focus.inpe_id}",
        type="heat_spot",
        lat=focus.lat,
        lng=focus.lng,
        area_id=None,
        confidence=_DEFAULT_CONFIDENCE,
        source="INPE_TERRABRASILIS",
        detected_at=detected_at,
        fetched_at=datetime.now(UTC),
        raw_data={
            "satelite": focus.satelite,
            "municipio": focus.municipio,
            "biome": focus.biome,
            "view_date": focus.view_date,
        },
    )


async def fetch_inpe_alerts(
    bbox: str | None = None,
    *,
    force_refresh: bool = False,
) -> tuple[list[OrbitalAlert], str | None]:
    """Fetch INPE active fire alerts.

    Checks in-memory cache first unless force_refresh=True.
    Returns (alerts, None) on success, ([], error_msg) on failure.
    Returns ([], None) when INPE_QUEIMADAS_ENABLED=false (not an error).
    """
    if not settings.inpe_queimadas_enabled:
        return [], None

    effective_bbox = bbox or settings.fire_bbox

    if not force_refresh:
        cached = cache_get(_CACHE_KEY)
        if cached is not None:
            return [OrbitalAlert.model_validate(a) for a in cached], None

    try:
        raw_focuses = await fetch_active_fires(bbox=effective_bbox)
    except httpx.HTTPError as exc:
        msg = f"INPE HTTP error: {type(exc).__name__}"
        logger.warning("INPE TerraBrasilis fetch failed: %s", type(exc).__name__)
        return [], msg
    except Exception as exc:
        msg = f"INPE error: {type(exc).__name__}"
        logger.warning("INPE TerraBrasilis unexpected error: %s", type(exc).__name__)
        return [], msg

    alerts = [_to_orbital_alert(f) for f in raw_focuses]
    ttl = settings.external_api_cache_ttl_minutes * 60
    cache_set(_CACHE_KEY, [a.model_dump(mode="json") for a in alerts], ttl)
    logger.info(
        "INPE TerraBrasilis: fetched %d active fire spots (bbox=%s)", len(alerts), effective_bbox
    )

    return alerts, None
