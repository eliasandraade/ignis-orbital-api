"""Aggregated orbital alerts service.

Combines fire spot data from multiple sources:
  - NASA FIRMS VIIRS  (requires NASA_FIRMS_MAP_KEY + NASA_FIRMS_ENABLED=true)
  - INPE TerraBrasilis WFS  (requires INPE_QUEIMADAS_ENABLED=true — public/free)
  - Demo fallback  (always available, no external call)

Design principles:
  - Never fails: individual provider errors are captured in `errors` field.
  - Graceful degradation: at least demo data is always returned.
  - Cache: aggregated result is cached; refreshed after ingest_all_sources().
  - No secrets in logs or responses: provider errors only include exception type.
"""

import logging
from datetime import UTC, datetime

from app.config import get_settings
from app.integrations._cache import cache_get, cache_set
from app.integrations.inpe_queimadas import service as inpe_service
from app.integrations.nasa_firms import service as nasa_service
from app.integrations.nasa_firms.schemas import (
    IngestResponse,
    OrbitalAlert,
    OrbitalAlertListResponse,
)

logger = logging.getLogger(__name__)
settings = get_settings()

_AGGREGATED_CACHE_KEY = "orbital_alerts:aggregated"


def _deduplicate(alerts: list[OrbitalAlert]) -> list[OrbitalAlert]:
    """Remove duplicate alerts by (rounded lat, rounded lng, source)."""
    seen: set[tuple] = set()
    result: list[OrbitalAlert] = []
    for alert in alerts:
        key = (round(alert.lat, 4), round(alert.lng, 4), alert.source)
        if key not in seen:
            seen.add(key)
            result.append(alert)
    return result


async def get_aggregated_alerts() -> OrbitalAlertListResponse:
    """Return aggregated orbital alerts from all enabled sources.

    Cache-first: returns cached aggregated result if warm.
    On cache miss: queries each enabled provider, merges, deduplicates.
    Falls back to demo data if all providers are disabled or fail.
    """
    ttl_minutes = settings.external_api_cache_ttl_minutes

    cached = cache_get(_AGGREGATED_CACHE_KEY)
    if cached is not None:
        items = [OrbitalAlert.model_validate(a) for a in cached["items"]]
        return OrbitalAlertListResponse(
            items=items,
            total=len(items),
            source_status="cached",
            cached_at=cached.get("cached_at"),
            providers_attempted=cached.get("providers_attempted", []),
            providers_successful=cached.get("providers_successful", []),
            fallback_used=cached.get("fallback_used", False),
        )

    providers_attempted: list[str] = []
    providers_successful: list[str] = []
    errors: list[str] = []
    all_alerts: list[OrbitalAlert] = []

    # --- NASA FIRMS ---
    nasa_active = settings.nasa_firms_enabled and bool(settings.nasa_firms_map_key)
    if nasa_active:
        providers_attempted.append("nasa_firms")
        nasa_cached = nasa_service.get_cached_nasa_alerts()
        if nasa_cached is not None:
            all_alerts.extend(nasa_cached)
            providers_successful.append("nasa_firms")
        else:
            # Cache miss: trigger an on-demand fetch
            result = await nasa_service.ingest_viirs()
            if result.status == "ok":
                fresh = nasa_service.get_cached_nasa_alerts() or []
                all_alerts.extend(fresh)
                providers_successful.append("nasa_firms")
            else:
                errors.extend(result.errors)

    # --- INPE TerraBrasilis ---
    if settings.inpe_queimadas_enabled:
        providers_attempted.append("inpe_queimadas")
        inpe_alerts, inpe_error = await inpe_service.fetch_inpe_alerts()
        if inpe_error is None:
            all_alerts.extend(inpe_alerts)
            if inpe_alerts:
                providers_successful.append("inpe_queimadas")
        else:
            errors.append(inpe_error)

    # --- Demo fallback ---
    fallback_used = len(all_alerts) == 0
    if fallback_used:
        all_alerts = list(nasa_service._DEMO_ALERTS)

    deduped = _deduplicate(all_alerts)
    now_str = datetime.now(UTC).isoformat()

    # Determine source_status
    if fallback_used and not providers_attempted:
        source_status = "disabled_missing_api_key"
    elif fallback_used:
        source_status = "unavailable"
    else:
        source_status = "live"

    # Cache aggregated result
    cache_set(
        _AGGREGATED_CACHE_KEY,
        {
            "items": [a.model_dump(mode="json") for a in deduped],
            "cached_at": now_str,
            "providers_attempted": providers_attempted,
            "providers_successful": providers_successful,
            "fallback_used": fallback_used,
        },
        ttl_minutes * 60,
    )

    return OrbitalAlertListResponse(
        items=deduped,
        total=len(deduped),
        source_status=source_status,  # type: ignore[arg-type]
        cached_at=now_str,
        providers_attempted=providers_attempted,
        providers_successful=providers_successful,
        fallback_used=fallback_used,
        errors=errors,
    )


async def ingest_all_sources() -> IngestResponse:
    """Trigger ingestion from all enabled sources and refresh cache.

    Returns:
      - status="ok" if all attempted providers succeeded
      - status="partial" if some succeeded
      - status="disabled_missing_api_key" if no providers are enabled
      - status="error" if all providers failed
    """
    providers_attempted: list[str] = []
    providers_successful: list[str] = []
    errors: list[str] = []
    total_fetched = 0
    total_inserted = 0
    total_skipped = 0

    # --- NASA FIRMS ---
    nasa_active = settings.nasa_firms_enabled and bool(settings.nasa_firms_map_key)
    if nasa_active:
        providers_attempted.append("nasa_firms")
        result = await nasa_service.ingest_viirs()
        if result.status == "ok":
            providers_successful.append("nasa_firms")
            total_fetched += result.records_fetched
            total_inserted += result.records_inserted
            total_skipped += result.records_skipped
        else:
            errors.extend(result.errors)

    # --- INPE TerraBrasilis ---
    if settings.inpe_queimadas_enabled:
        providers_attempted.append("inpe_queimadas")
        inpe_alerts, inpe_error = await inpe_service.fetch_inpe_alerts(force_refresh=True)
        if inpe_error is None:
            providers_successful.append("inpe_queimadas")
            total_fetched += len(inpe_alerts)
            total_inserted += len(inpe_alerts)
        else:
            errors.append(inpe_error)

    # Invalidate aggregated cache so next GET rebuilds with fresh data
    # Setting a 1s TTL causes cache_get to return None on the next call
    cache_set(_AGGREGATED_CACHE_KEY, None, 1)

    if not providers_attempted:
        return IngestResponse(
            status="disabled_missing_api_key",
            message=(
                "Nenhuma fonte habilitada. "
                "Configure NASA_FIRMS_ENABLED=true e/ou INPE_QUEIMADAS_ENABLED=true."
            ),
            fallback_used=True,
        )

    if providers_successful:
        if len(providers_successful) == len(providers_attempted):
            status: str = "ok"
        else:
            status = "partial"
        message = (
            f"Ingestão concluída. Fontes: {', '.join(providers_successful)}. "
            f"{total_inserted} focos ingeridos de {total_fetched} recebidos "
            f"({total_skipped} descartados)."
        )
    else:
        status = "error"
        message = "Todas as fontes falharam. Veja o campo errors para detalhes."

    return IngestResponse(
        status=status,  # type: ignore[arg-type]
        message=message,
        records_fetched=total_fetched,
        records_inserted=total_inserted,
        records_skipped=total_skipped,
        providers_successful=providers_successful,
        fallback_used=(len(providers_successful) == 0),
        errors=errors,
    )
