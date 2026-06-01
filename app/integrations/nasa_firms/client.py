"""HTTP client for NASA FIRMS API.

Requires NASA_FIRMS_MAP_KEY to be set. Without the key the client raises
MissingApiKeyError instead of making any network call.
"""

import csv
import io
from datetime import UTC, datetime, timedelta

import httpx

from app.config import get_settings

settings = get_settings()


class MissingApiKeyError(RuntimeError):
    """Raised when NASA_FIRMS_MAP_KEY is not configured."""


def _require_key() -> str:
    key = settings.nasa_firms_map_key
    if not key:
        raise MissingApiKeyError(
            "NASA_FIRMS_MAP_KEY não configurada. "
            "Defina a variável de ambiente para ativar a ingestão de dados orbitais."
        )
    return key


async def fetch_viirs_csv(bbox: str, date: str | None = None) -> list[dict]:
    """Fetch VIIRS SNPP NRT fire spots for the given bounding box.

    Args:
        bbox: "lng_min,lat_min,lng_max,lat_max" — e.g. "-45.0,-12.0,-34.5,2.5"
        date: ISO date string (YYYY-MM-DD). Defaults to yesterday.

    Returns:
        List of dicts parsed from the FIRMS CSV response.

    Raises:
        MissingApiKeyError: when NASA_FIRMS_MAP_KEY is absent.
        httpx.HTTPError: on network or HTTP failure.
    """
    key = _require_key()
    if date is None:
        date = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")

    url = f"{settings.nasa_firms_base_url}/area/csv/{key}/VIIRS_SNPP_NRT/{bbox}/1/{date}"
    async with httpx.AsyncClient(
        timeout=settings.external_api_timeout_seconds,
        headers={"User-Agent": "IGNIS-Orbital/1.0 (FIAP GS 2026; academic project)"},
    ) as http:
        response = await http.get(url)
        response.raise_for_status()

    reader = csv.DictReader(io.StringIO(response.text))
    return list(reader)
