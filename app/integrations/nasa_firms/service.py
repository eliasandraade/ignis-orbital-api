"""NASA FIRMS service layer.

Honest-state contract (Sprint 0):

- Without NASA_FIRMS_MAP_KEY the list is empty with
  source_status="disabled_missing_api_key". Demo alerts are returned only when
  ORBITAL_ALERTS_DEMO_MODE=true, flagged with source_status="demo" and
  is_demo=True on every item. Demo data is never reported as "live".
- With the key, alerts come from NASA FIRMS (VIIRS SNPP NRT) and are kept in
  the in-memory cache only. Nothing is written to the database yet: responses
  carry persisted=False and records_inserted=0. Database persistence (table
  orbital_alerts + PostGIS) is planned for Phase 1.
- Upstream failures return source_status="unavailable" with an empty list.
  Error messages expose only the exception type, because the FIRMS URL embeds
  the MAP_KEY.

A heat spot is a satellite thermal anomaly, not a confirmed fire.
"""

import uuid
from datetime import UTC, datetime

from app.config import get_settings
from app.integrations._cache import cache_get, cache_set
from app.integrations.nasa_firms import client as firms_client
from app.integrations.nasa_firms.client import MissingApiKeyError
from app.integrations.nasa_firms.schemas import (
    OrbitalAlert,
    OrbitalAlertListResponse,
)

settings = get_settings()

# Default bbox for CE/PI/MA/TO coverage (lng_min,lat_min,lng_max,lat_max)
_DEFAULT_BBOX = "-45.0,-12.0,-34.5,2.5"

# Confidence string mappings from FIRMS CSV
_CONFIDENCE_MAP = {"low": 25, "nominal": 60, "high": 90}

# After an upstream failure, wait before calling NASA again (protects quota
# and avoids hammering an unavailable service from a public endpoint).
_FAILURE_BACKOFF_SECONDS = 300

_MISSING_KEY_MESSAGE = (
    "NASA FIRMS desabilitada: NASA_FIRMS_MAP_KEY não configurada. Nenhum foco real disponível."
)

# Fictitious alerts — only served when ORBITAL_ALERTS_DEMO_MODE=true.
_DEMO_ALERTS: list[OrbitalAlert] = [
    OrbitalAlert(
        id="demo-firms-001",
        type="heat_spot",
        lat=-4.2,
        lng=-38.5,
        area_id=None,
        confidence=75,
        source="DEMO",
        detected_at=datetime(2026, 5, 31, 10, 0, 0, tzinfo=UTC),
        fetched_at=datetime(2026, 5, 31, 12, 0, 0, tzinfo=UTC),
        is_demo=True,
    ),
    OrbitalAlert(
        id="demo-firms-002",
        type="heat_spot",
        lat=-4.5,
        lng=-39.1,
        area_id=None,
        confidence=45,
        source="DEMO",
        detected_at=datetime(2026, 5, 31, 9, 30, 0, tzinfo=UTC),
        fetched_at=datetime(2026, 5, 31, 12, 0, 0, tzinfo=UTC),
        is_demo=True,
    ),
    OrbitalAlert(
        id="demo-firms-003",
        type="heat_spot",
        lat=-3.8,
        lng=-40.2,
        area_id=None,
        confidence=85,
        source="DEMO",
        detected_at=datetime(2026, 5, 30, 22, 0, 0, tzinfo=UTC),
        fetched_at=datetime(2026, 5, 31, 6, 0, 0, tzinfo=UTC),
        is_demo=True,
    ),
]


class FirmsUnavailableError(RuntimeError):
    """Upstream fetch failed. The message is safe to expose (no MAP_KEY)."""


def _parse_confidence(raw: str) -> int:
    raw = raw.strip().lower()
    if raw in _CONFIDENCE_MAP:
        return _CONFIDENCE_MAP[raw]
    try:
        return int(raw)
    except ValueError:
        return 50


def _stable_alert_id(row: dict) -> str:
    """Deterministic id so the same detection keeps its id across fetches."""
    key = "|".join(
        str(row.get(field, "")).strip()
        for field in ("latitude", "longitude", "acq_date", "acq_time", "satellite")
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"firms:viirs:{key}"))


def _csv_row_to_alert(row: dict, fetched_at: datetime | None = None) -> OrbitalAlert | None:
    try:
        lat = float(row["latitude"])
        lng = float(row["longitude"])
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return None
        confidence = _parse_confidence(row.get("confidence", "50"))
        # Skip very low confidence rows (likely false positives)
        if confidence < 25:
            return None

        acq_date = row.get("acq_date", "")
        acq_time = row.get("acq_time", "0000").zfill(4)
        detected_at = datetime.strptime(
            f"{acq_date} {acq_time[:2]}:{acq_time[2:]}", "%Y-%m-%d %H:%M"
        ).replace(tzinfo=UTC)

        return OrbitalAlert(
            id=_stable_alert_id(row),
            type="heat_spot",
            lat=lat,
            lng=lng,
            area_id=None,
            confidence=confidence,
            source="NASA_FIRMS_VIIRS",
            detected_at=detected_at,
            fetched_at=fetched_at or datetime.now(UTC),
            raw_data={k: v for k, v in row.items()},
        )
    except (KeyError, ValueError):
        return None


def _cache_key(bbox: str) -> str:
    return f"firms:viirs:{bbox}"


def _failure_key(bbox: str) -> str:
    return f"firms:viirs:failure:{bbox}"


async def _fetch_and_cache(bbox: str) -> tuple[list[OrbitalAlert], int, datetime]:
    """Fetch from NASA, cache the parsed alerts and return (alerts, rows, fetched_at).

    Raises:
        MissingApiKeyError: key absent.
        FirmsUnavailableError: network/HTTP/format failure (safe message).
    """
    try:
        rows = await firms_client.fetch_viirs_csv(bbox)
    except MissingApiKeyError:
        raise
    except Exception as exc:  # any upstream failure is "unavailable"
        message = f"NASA FIRMS indisponível ({type(exc).__name__})"
        cache_set(_failure_key(bbox), message, _FAILURE_BACKOFF_SECONDS)
        raise FirmsUnavailableError(message) from None

    fetched_at = datetime.now(UTC)
    alerts = [a for row in rows if (a := _csv_row_to_alert(row, fetched_at)) is not None]
    # Deduplicate by deterministic id (FIRMS may repeat rows across windows)
    alerts = list({a.id: a for a in alerts}.values())
    cache_set(
        _cache_key(bbox),
        (alerts, fetched_at),
        settings.external_api_cache_ttl_minutes * 60,
    )
    return alerts, len(rows), fetched_at


def _demo_response() -> OrbitalAlertListResponse:
    return OrbitalAlertListResponse(
        items=_DEMO_ALERTS,
        total=len(_DEMO_ALERTS),
        source_status="demo",
        data_origin="demo",
        persisted=False,
        message="Modo demonstrativo: focos fictícios, não representam detecções reais.",
    )


async def list_alerts(bbox: str | None = None) -> OrbitalAlertListResponse:
    """Return orbital heat-spot alerts with an honest source_status."""
    bbox = bbox or _DEFAULT_BBOX

    if not settings.nasa_firms_map_key:
        if settings.orbital_alerts_demo_mode:
            return _demo_response()
        return OrbitalAlertListResponse(
            items=[],
            total=0,
            source_status="disabled_missing_api_key",
            data_origin="none",
            message=_MISSING_KEY_MESSAGE,
        )

    cached = cache_get(_cache_key(bbox))
    if cached is not None:
        alerts, fetched_at = cached
        status = "cached"
    else:
        recent_failure = cache_get(_failure_key(bbox))
        if recent_failure is not None:
            return OrbitalAlertListResponse(
                items=[], total=0, source_status="unavailable", message=recent_failure
            )
        try:
            alerts, _rows, fetched_at = await _fetch_and_cache(bbox)
        except MissingApiKeyError:
            return OrbitalAlertListResponse(
                items=[],
                total=0,
                source_status="disabled_missing_api_key",
                message=_MISSING_KEY_MESSAGE,
            )
        except FirmsUnavailableError as exc:
            return OrbitalAlertListResponse(
                items=[], total=0, source_status="unavailable", message=str(exc)
            )
        status = "live"

    return OrbitalAlertListResponse(
        items=alerts,
        total=len(alerts),
        source_status=status,  # type: ignore[arg-type]
        data_origin="nasa_firms",
        persisted=False,
        since=None,
        cached_at=fetched_at.isoformat() if status == "cached" else None,
        fetched_at=fetched_at.isoformat(),
        message="Dados NASA FIRMS mantidos apenas em cache de memória; não persistidos em banco.",
    )
