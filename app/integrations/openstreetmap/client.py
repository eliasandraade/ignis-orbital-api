"""HTTP client for Nominatim reverse geocoding.

Nominatim usage policy requires:
  - A descriptive User-Agent identifying the application.
  - No more than 1 request per second.
  - Caching mandatory — do not repeat identical requests.

See: https://operations.osmfoundation.org/policies/nominatim/
"""

import httpx

from app.config import get_settings

settings = get_settings()

_HEADERS = {
    # Nominatim's usage policy asks for an identifying agent with a contact URL.
    "User-Agent": "IGNIS-Orbital/1.0 (Andrade Systems; +https://github.com/eliasandraade/ignis-orbital-api)",
    "Accept-Language": "pt-BR,pt;q=0.9",
}


async def fetch_reverse_geocoding(lat: float, lng: float) -> dict:
    """Perform reverse geocoding via Nominatim.

    Returns raw JSON from the API.  Raises httpx.HTTPError on failure.
    Caching must be applied at the service layer before calling this function.
    """
    url = f"{settings.osm_nominatim_base_url}/reverse"
    params = {"lat": lat, "lon": lng, "format": "json", "addressdetails": 1}
    async with httpx.AsyncClient(
        timeout=settings.external_api_timeout_seconds,
        headers=_HEADERS,
    ) as http:
        response = await http.get(url, params=params)
        response.raise_for_status()
        return response.json()
