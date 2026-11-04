from fastapi import APIRouter, Depends, Query

from app.core.rate_limit import rate_limit
from app.integrations.open_meteo.schemas import WeatherRiskResponse
from app.integrations.open_meteo.service import get_weather_risk

router = APIRouter(prefix="/api/v1/environment", tags=["meteorologia"])


@router.get(
    "/weather-risk",
    dependencies=[Depends(rate_limit("weather-risk", limit=60))],
)
async def weather_risk(
    lat: float = Query(..., ge=-90, le=90, description="Latitude"),
    lng: float = Query(..., ge=-180, le=180, description="Longitude"),
) -> WeatherRiskResponse:
    """Return current weather-based fire risk for a coordinate pair.

    Data sourced from Open-Meteo (open-meteo.com) — no API key required.
    Results are cached per location to avoid excessive external calls.
    Marked as 'cached' when served from cache, 'live' when freshly fetched,
    'unavailable' when Open-Meteo is unreachable.
    """
    return await get_weather_risk(lat, lng)
