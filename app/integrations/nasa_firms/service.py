"""NASA FIRMS service layer.

When NASA_FIRMS_ENABLED=true and NASA_FIRMS_MAP_KEY is set, ingest_viirs()
fetches real VIIRS SNPP NRT data, parses rows, and caches results in memory.
list_alerts() reads from that cache; falls back to demo data otherwise so
the frontend always has content to display.

API key guard: the key is never logged or included in error messages.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.integrations._cache import cache_get, cache_set
from app.integrations.nasa_firms import client as firms_client
from app.integrations.nasa_firms.client import MissingApiKeyError
from app.integrations.nasa_firms.schemas import (
    IngestResponse,
    OrbitalAlert,
    OrbitalAlertListResponse,
)

logger = logging.getLogger(__name__)
settings = get_settings()

_CACHE_KEY = "nasa_firms:alerts"

# Confidence string mappings from FIRMS CSV
_CONFIDENCE_MAP = {"low": 25, "nominal": 60, "high": 90}

# Demo alerts — always available as fallback when key is absent or ingest hasn't run
_DEMO_ALERTS: list[OrbitalAlert] = [
    OrbitalAlert(
        id="demo-firms-001",
        type="heat_spot",
        lat=-4.2,
        lng=-38.5,
        area_id=None,
        confidence=75,
        source="NASA_FIRMS_VIIRS",
        detected_at=datetime(2026, 5, 31, 10, 0, 0, tzinfo=UTC),
        fetched_at=datetime(2026, 5, 31, 12, 0, 0, tzinfo=UTC),
    ),
    OrbitalAlert(
        id="demo-firms-002",
        type="heat_spot",
        lat=-4.5,
        lng=-39.1,
        area_id=None,
        confidence=45,
        source="NASA_FIRMS_MODIS",
        detected_at=datetime(2026, 5, 31, 9, 30, 0, tzinfo=UTC),
        fetched_at=datetime(2026, 5, 31, 12, 0, 0, tzinfo=UTC),
    ),
    OrbitalAlert(
        id="demo-firms-003",
        type="heat_spot",
        lat=-3.8,
        lng=-40.2,
        area_id=None,
        confidence=85,
        source="NASA_FIRMS_VIIRS",
        detected_at=datetime(2026, 5, 30, 22, 0, 0, tzinfo=UTC),
        fetched_at=datetime(2026, 5, 31, 6, 0, 0, tzinfo=UTC),
    ),
]


def _parse_confidence(raw: str) -> int:
    raw = raw.strip().lower()
    if raw in _CONFIDENCE_MAP:
        return _CONFIDENCE_MAP[raw]
    try:
        return int(raw)
    except ValueError:
        return 50


def _csv_row_to_alert(row: dict) -> OrbitalAlert | None:
    try:
        lat = float(row["latitude"])
        lng = float(row["longitude"])
        confidence = _parse_confidence(row.get("confidence", "50"))
        if confidence < 25:
            return None

        acq_date = row.get("acq_date", "")
        acq_time = row.get("acq_time", "0000").zfill(4)
        detected_at = datetime.strptime(
            f"{acq_date} {acq_time[:2]}:{acq_time[2:]}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=UTC)

        return OrbitalAlert(
            id=str(uuid.uuid4()),
            type="heat_spot",
            lat=lat,
            lng=lng,
            area_id=None,
            confidence=confidence,
            source="NASA_FIRMS_VIIRS",
            detected_at=detected_at,
            fetched_at=datetime.now(UTC),
            raw_data={k: v for k, v in row.items()},
        )
    except (KeyError, ValueError):
        return None


def get_cached_nasa_alerts() -> list[OrbitalAlert] | None:
    """Return cached NASA FIRMS alerts, or None if cache is empty/expired."""
    cached = cache_get(_CACHE_KEY)
    if cached is None:
        return None
    return [OrbitalAlert.model_validate(a) for a in cached]


def list_alerts() -> OrbitalAlertListResponse:
    """Return NASA FIRMS orbital alerts (backwards-compatible single-provider endpoint).

    When NASA_FIRMS_ENABLED=true and key is set, reads from in-memory cache.
    Otherwise returns demo data so the frontend always has content.
    Prefer get_aggregated_alerts() (orbital_alerts_service) for full multi-source view.
    """
    has_key = bool(settings.nasa_firms_map_key)
    enabled = settings.nasa_firms_enabled

    if enabled and has_key:
        cached_alerts = get_cached_nasa_alerts()
        if cached_alerts is not None:
            return OrbitalAlertListResponse(
                items=cached_alerts,
                total=len(cached_alerts),
                source_status="cached",
                cached_at=datetime.now(UTC).isoformat(),
                providers_successful=["nasa_firms"],
            )
        # Enabled + key present but cache empty (ingest not yet run)
        return OrbitalAlertListResponse(
            items=_DEMO_ALERTS,
            total=len(_DEMO_ALERTS),
            source_status="live",
            cached_at=datetime.now(UTC).isoformat(),
            fallback_used=True,
        )

    return OrbitalAlertListResponse(
        items=_DEMO_ALERTS,
        total=len(_DEMO_ALERTS),
        source_status="disabled_missing_api_key",
        since=None,
        cached_at=datetime.now(UTC).isoformat(),
        fallback_used=True,
    )


async def ingest_viirs(bbox: str | None = None) -> IngestResponse:
    """Fetch NASA FIRMS VIIRS data and persist to in-memory cache.

    Guards:
    - Returns disabled status when NASA_FIRMS_MAP_KEY is absent.
    - Returns disabled status when NASA_FIRMS_ENABLED=false.
    - On HTTP/network error returns error status without propagating (safe fallback).
    API key is never logged or exposed in error messages.
    """
    has_key = bool(settings.nasa_firms_map_key)
    enabled = settings.nasa_firms_enabled

    if not has_key:
        return IngestResponse(
            status="disabled_missing_api_key",
            message=(
                "Ingestão NASA FIRMS desabilitada: NASA_FIRMS_MAP_KEY não configurada. "
                "Cadastre-se em firms.modaps.eosdis.nasa.gov e configure a variável."
            ),
            fallback_used=True,
        )

    if not enabled:
        return IngestResponse(
            status="disabled_missing_api_key",
            message="Ingestão NASA FIRMS desabilitada: NASA_FIRMS_ENABLED=false.",
            fallback_used=True,
        )

    effective_bbox = bbox or settings.fire_bbox
    target_date = (datetime.now(UTC) - timedelta(days=settings.fire_lookback_days)).strftime(
        "%Y-%m-%d"
    )

    try:
        rows = await firms_client.fetch_viirs_csv(bbox=effective_bbox, date=target_date)
    except MissingApiKeyError as exc:
        return IngestResponse(
            status="disabled_missing_api_key",
            message=str(exc),
            fallback_used=True,
        )
    except Exception as exc:
        logger.warning("NASA FIRMS fetch error: %s", type(exc).__name__)
        return IngestResponse(
            status="error",
            message=f"Erro ao buscar dados NASA FIRMS: {type(exc).__name__}",
            errors=[f"NASA FIRMS: {type(exc).__name__}"],
            fallback_used=True,
        )

    fetched = len(rows)
    alerts: list[OrbitalAlert] = []
    skipped = 0
    for row in rows:
        alert = _csv_row_to_alert(row)
        if alert is None:
            skipped += 1
        else:
            alerts.append(alert)

    ttl = settings.external_api_cache_ttl_minutes * 60
    cache_set(_CACHE_KEY, [a.model_dump(mode="json") for a in alerts], ttl)
    logger.info(
        "NASA FIRMS ingest: fetched=%d parsed=%d skipped=%d date=%s",
        fetched,
        len(alerts),
        skipped,
        target_date,
    )

    return IngestResponse(
        status="ok",
        message=(
            f"NASA FIRMS VIIRS: {len(alerts)} focos ingeridos "
            f"de {fetched} linhas ({skipped} descartados por confiança baixa)."
        ),
        records_fetched=fetched,
        records_inserted=len(alerts),
        records_skipped=skipped,
        providers_successful=["nasa_firms"],
        fallback_used=False,
    )
