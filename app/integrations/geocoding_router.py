from fastapi import APIRouter, Depends, Query

from app.core.rate_limit import rate_limit
from app.integrations.openstreetmap.schemas import ReverseGeocodingResponse
from app.integrations.openstreetmap.service import reverse_geocode

router = APIRouter(prefix="/api/v1/geocoding", tags=["geocoding"])


@router.get(
    "/reverse",
    response_model=ReverseGeocodingResponse,
    dependencies=[Depends(rate_limit("geocoding", limit=30))],
)
async def reverse_geocoding(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lng: float = Query(..., ge=-180, le=180, description="Longitude"),
) -> ReverseGeocodingResponse:
    """Resolve coordinates to a human-readable address via Nominatim.

    Results are cached per rounded coordinate (~111 m grid) for the configured
    cache TTL (default 60 min).  Returns a controlled empty response if the
    Nominatim service is unavailable — never raises a 5xx to the caller.
    """
    return await reverse_geocode(lat, lng)
