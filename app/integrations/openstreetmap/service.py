"""OpenStreetMap/Nominatim reverse geocoding service.

Caches results by rounded coordinates to avoid repeated calls.
Coordinates are rounded to 3 decimal places (~111 m precision) for the cache key.

Nominatim policy: mandatory caching, ≤1 req/s.  This service enforces caching;
rate limiting is handled by the fact that repeated coordinates hit the cache.
"""

from datetime import UTC, datetime

import httpx

from app.config import get_settings
from app.integrations._cache import cache_get, cache_set
from app.integrations.openstreetmap import client as osm_client
from app.integrations.openstreetmap.schemas import ReverseGeocodingResponse

settings = get_settings()


def _round_coord(value: float, precision: int = 3) -> float:
    return round(value, precision)


def _extract_address_field(address: dict, *keys: str) -> str | None:
    for key in keys:
        if val := address.get(key):
            return str(val)
    return None


async def reverse_geocode(lat: float, lng: float) -> ReverseGeocodingResponse:
    """Resolve coordinates to a human-readable address.

    Returns a controlled response on any error; never propagates exceptions
    to the caller so that geocoding failures don't break the main workflow.
    """
    ttl_seconds = settings.external_api_cache_ttl_minutes * 60
    lat_r = _round_coord(lat)
    lng_r = _round_coord(lng)
    cache_key = f"osm_nominatim:{lat_r}:{lng_r}"

    cached = cache_get(cache_key)
    if cached is not None:
        return ReverseGeocodingResponse.model_validate({**cached, "cached": True})

    now_str = datetime.now(UTC).isoformat()

    try:
        raw = await osm_client.fetch_reverse_geocoding(lat_r, lng_r)
    except (httpx.HTTPError, Exception):
        return ReverseGeocodingResponse(
            latitude=lat,
            longitude=lng,
            display_name=None,
            municipality=None,
            state=None,
            country=None,
            cached=False,
            fetched_at=now_str,
        )

    address = raw.get("address", {})
    response = ReverseGeocodingResponse(
        latitude=lat,
        longitude=lng,
        display_name=raw.get("display_name"),
        municipality=_extract_address_field(address, "city", "town", "village", "municipality"),
        state=address.get("state"),
        country=address.get("country"),
        cached=False,
        fetched_at=now_str,
    )

    cache_set(cache_key, response.model_dump(), ttl_seconds)
    return response
