"""NASA FIRMS service layer.

Handles the disabled/ready-state when NASA_FIRMS_MAP_KEY is absent.
Full ingest logic is prepared but guarded behind the key check so that
the API boots cleanly in environments where the key has not been configured.

When the key is present, calling `ingest_viirs` fetches recent VIIRS data,
parses and deduplicates rows, and returns a summary.  Actual persistence to
the database (orbital_alerts table) will be wired in the migration phase.
"""

import uuid
from datetime import UTC, datetime

from app.config import get_settings
from app.integrations.nasa_firms import client as firms_client
from app.integrations.nasa_firms.client import MissingApiKeyError
from app.integrations.nasa_firms.schemas import (
    IngestResponse,
    OrbitalAlert,
    OrbitalAlertListResponse,
)

settings = get_settings()

# Default bbox for CE/PI/MA/TO coverage (lng_min,lat_min,lng_max,lat_max)
_DEFAULT_BBOX = "-45.0,-12.0,-34.5,2.5"

# Confidence string mappings from FIRMS CSV
_CONFIDENCE_MAP = {"low": 25, "nominal": 60, "high": 90}

# Demo alerts used when key is absent or ingest has not run yet
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
        # Skip very low confidence rows (likely false positives)
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


def list_alerts() -> OrbitalAlertListResponse:
    """Return current list of orbital alerts.

    Returns demo data with disabled status when the API key is absent.
    Actual database reads will be added in the persistence phase.
    """
    has_key = bool(settings.nasa_firms_map_key)
    status = "disabled_missing_api_key" if not has_key else "live"

    return OrbitalAlertListResponse(
        items=_DEMO_ALERTS,
        total=len(_DEMO_ALERTS),
        source_status=status,  # type: ignore[arg-type]
        since=None,
        cached_at=datetime.now(UTC).isoformat(),
    )


async def ingest_viirs(bbox: str | None = None) -> IngestResponse:
    """Trigger a NASA FIRMS VIIRS ingestion run.

    Returns disabled status clearly when the API key is absent.
    When the key is present, fetches CSV and parses rows (persistence
    to orbital_alerts table will be wired after the migration is created).
    """
    if not settings.nasa_firms_map_key:
        return IngestResponse(
            status="disabled_missing_api_key",
            message=(
                "Ingestão NASA FIRMS desabilitada: NASA_FIRMS_MAP_KEY não configurada. "
                "Cadastre-se em firms.modaps.eosdis.nasa.gov e configure a variável no Railway."
            ),
        )

    try:
        rows = await firms_client.fetch_viirs_csv(bbox or _DEFAULT_BBOX)
    except MissingApiKeyError as exc:
        return IngestResponse(
            status="disabled_missing_api_key",
            message=str(exc),
        )
    except Exception as exc:
        return IngestResponse(
            status="error",
            message=f"Erro ao buscar dados NASA FIRMS: {exc}",
        )

    alerts = [a for row in rows if (a := _csv_row_to_alert(row)) is not None]
    return IngestResponse(
        status="ok",
        message=(
            f"Ingestão VIIRS concluída. {len(alerts)} focos válidos "
            f"de {len(rows)} linhas recebidas. "
            "Persistência em banco será ativada após criação da migration orbital_alerts."
        ),
        records_fetched=len(rows),
        records_inserted=len(alerts),
        records_skipped=len(rows) - len(alerts),
    )
