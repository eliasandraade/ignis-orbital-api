"""HTTP client for Open-Meteo API (no API key required)."""

import httpx

from app.config import get_settings

settings = get_settings()

_CURRENT_VARIABLES = (
    "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,precipitation"
)


async def fetch_current_weather(lat: float, lng: float) -> dict:
    """Fetch current weather from Open-Meteo for the given coordinates.

    Returns a dict with current weather values, or raises httpx.HTTPError on failure.
    """
    url = f"{settings.open_meteo_base_url}/forecast"
    params = {
        "latitude": lat,
        "longitude": lng,
        "current": _CURRENT_VARIABLES,
        "wind_speed_unit": "kmh",
        "timezone": "America/Fortaleza",
    }
    async with httpx.AsyncClient(
        timeout=settings.external_api_timeout_seconds,
        headers={
            "User-Agent": "IGNIS-Orbital/1.0 (Andrade Systems; +https://github.com/eliasandraade/ignis-orbital-api)"
        },
    ) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()
