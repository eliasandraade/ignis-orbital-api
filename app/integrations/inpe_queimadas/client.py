"""HTTP client for INPE TerraBrasilis WFS fire data.

Source: TerraBrasilis GeoServer — ams1h:active-fire-today layer
URL: https://terrabrasilis.dpi.inpe.br/geoserver/ows
Protocol: OGC WFS 1.0.0 — GeoJSON output
Authentication: none (public layer)
Validated: 2026-06-01 — returns live data, no API key required.

The WFS `resultType=hits` is NOT supported by this server (always returns 0).
Use maxFeatures to limit response size; bbox filters by geographic area.
"""

import contextlib
from datetime import datetime

import httpx

from app.config import get_settings
from app.integrations.inpe_queimadas.schemas import InpeFocus

settings = get_settings()

_DEFAULT_WFS_URL = "https://terrabrasilis.dpi.inpe.br/geoserver/ows"
_LAYER = "ams1h:active-fire-today"
_MAX_FEATURES = 500
_USER_AGENT = "IGNIS-Orbital/1.0 (FIAP GS 2026; academic project)"


async def fetch_active_fires(bbox: str, max_features: int = _MAX_FEATURES) -> list[InpeFocus]:
    """Fetch today's active fire spots from INPE TerraBrasilis WFS.

    Args:
        bbox: Bounding box "lng_min,lat_min,lng_max,lat_max" — e.g. "-45.0,-12.0,-34.5,2.5"
        max_features: Maximum number of features to request (default 500).

    Returns:
        List of InpeFocus objects parsed from GeoJSON FeatureCollection.

    Raises:
        httpx.HTTPError: on network or HTTP failure.
    """
    base_url = settings.inpe_queimadas_url or _DEFAULT_WFS_URL

    params = {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetFeature",
        "typeName": _LAYER,
        "outputFormat": "application/json",
        "maxFeatures": str(max_features),
        "bbox": f"{bbox},EPSG:4326",
    }

    async with httpx.AsyncClient(
        timeout=settings.external_api_timeout_seconds,
        headers={"User-Agent": _USER_AGENT},
    ) as http:
        response = await http.get(base_url, params=params)
        response.raise_for_status()

    data = response.json()
    results: list[InpeFocus] = []

    for feature in data.get("features", []):
        props = feature.get("properties", {})
        coords = feature.get("geometry", {}).get("coordinates", [])
        if len(coords) < 2:
            continue

        lng, lat = float(coords[0]), float(coords[1])

        viewed_at: datetime | None = None
        raw_dt = props.get("viewed_at")
        if raw_dt:
            with contextlib.suppress(ValueError, TypeError):
                viewed_at = datetime.fromisoformat(raw_dt)

        results.append(
            InpeFocus(
                feature_id=feature.get("id", ""),
                inpe_id=int(props.get("id", 0)),
                lat=lat,
                lng=lng,
                view_date=props.get("view_date", ""),
                viewed_at=viewed_at,
                satelite=props.get("satelite"),
                municipio=props.get("municipio"),
                biome=props.get("biome"),
            )
        )

    return results
