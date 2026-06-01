"""Open-Meteo weather risk service.

Fetches current weather data, applies a risk scoring algorithm, and caches
results to avoid repeated calls to the external API.

Risk score (0-100):
  - High temperature increases risk (up to +30 pts)
  - Low relative humidity increases risk (up to +35 pts)
  - High wind speed increases risk (up to +25 pts)
  - Recent precipitation reduces risk (up to -15 pts)

Levels: low 0-25 | moderate 26-50 | high 51-75 | critical 76-100
"""

from datetime import UTC, datetime

import httpx

from app.config import get_settings
from app.integrations._cache import cache_get, cache_set
from app.integrations.open_meteo import client as om_client
from app.integrations.open_meteo.schemas import WeatherRiskFactor, WeatherRiskResponse

settings = get_settings()

_UNAVAILABLE_RESPONSE_TEMPLATE = WeatherRiskResponse(
    source_status="unavailable",
    latitude=0.0,
    longitude=0.0,
    temperature_c=None,
    relative_humidity=None,
    wind_speed_kmh=None,
    wind_direction=None,
    precipitation_mm=None,
    risk_level="low",
    risk_score=0,
    factors=[],
    recommendation="Fonte meteorológica externa indisponível. Consulte a equipe de campo.",
    fetched_at=datetime.now(UTC).isoformat(),
    cache_ttl_minutes=0,
)


def _round_coord(value: float, precision: int = 2) -> float:
    return round(value, precision)


def _calculate_risk(
    temp: float | None,
    humidity: float | None,
    wind_speed: float | None,
    precipitation: float | None,
) -> tuple[int, str, list[WeatherRiskFactor], str]:
    score = 0
    factors: list[WeatherRiskFactor] = []

    if temp is not None:
        if temp >= 40:
            score += 30
            factors.append(WeatherRiskFactor(
                name="Temperatura extrema",
                impact="high",
                description=f"{temp:.1f}°C — risco de ignição elevado",
            ))
        elif temp >= 35:
            score += 20
            factors.append(WeatherRiskFactor(
                name="Temperatura alta",
                impact="moderate",
                description=f"{temp:.1f}°C — condições favoráveis ao fogo",
            ))
        elif temp >= 28:
            score += 8
            factors.append(WeatherRiskFactor(
                name="Temperatura elevada",
                impact="low",
                description=f"{temp:.1f}°C — atenção recomendada",
            ))
        else:
            factors.append(WeatherRiskFactor(
                name="Temperatura",
                impact="low",
                description=f"{temp:.1f}°C — sem agravamento",
            ))

    if humidity is not None:
        if humidity <= 20:
            score += 35
            factors.append(WeatherRiskFactor(
                name="Umidade crítica",
                impact="high",
                description=f"{humidity:.0f}% — vegetação ressecada, risco máximo",
            ))
        elif humidity <= 40:
            score += 22
            factors.append(WeatherRiskFactor(
                name="Umidade baixa",
                impact="moderate",
                description=f"{humidity:.0f}% — vegetação susceptível",
            ))
        elif humidity <= 60:
            score += 8
            factors.append(WeatherRiskFactor(
                name="Umidade moderada",
                impact="low",
                description=f"{humidity:.0f}% — atenção moderada",
            ))
        else:
            factors.append(WeatherRiskFactor(
                name="Umidade",
                impact="low",
                description=f"{humidity:.0f}% — vegetação hidratada",
            ))

    if wind_speed is not None:
        if wind_speed >= 50:
            score += 25
            factors.append(WeatherRiskFactor(
                name="Vento muito forte",
                impact="high",
                description=f"{wind_speed:.1f} km/h — propagação rápida de incêndios",
            ))
        elif wind_speed >= 30:
            score += 15
            factors.append(WeatherRiskFactor(
                name="Vento forte",
                impact="moderate",
                description=f"{wind_speed:.1f} km/h — risco de propagação aumentado",
            ))
        elif wind_speed >= 15:
            score += 6
            factors.append(WeatherRiskFactor(
                name="Vento moderado",
                impact="low",
                description=f"{wind_speed:.1f} km/h — propagação possível",
            ))
        else:
            factors.append(WeatherRiskFactor(
                name="Vento",
                impact="low",
                description=f"{wind_speed:.1f} km/h — baixo impacto",
            ))

    if precipitation is not None and precipitation > 0:
        if precipitation >= 10:
            score = max(0, score - 15)
            factors.append(WeatherRiskFactor(
                name="Chuva recente",
                impact="low",
                description=f"{precipitation:.1f} mm — vegetação úmida, risco reduzido",
            ))
        elif precipitation >= 1:
            score = max(0, score - 6)
            factors.append(WeatherRiskFactor(
                name="Precipitação leve",
                impact="low",
                description=f"{precipitation:.1f} mm — pequena redução de risco",
            ))

    score = min(100, max(0, score))

    if score <= 25:
        level = "low"
        recommendation = (
            "Condições meteorológicas não apresentam risco significativo. Vigilância de rotina."
        )
    elif score <= 50:
        level = "moderate"
        recommendation = (
            "Condições moderadas de risco. Aumentar patrulhamento e alertar equipes de campo."
        )
    elif score <= 75:
        level = "high"
        recommendation = (
            "Risco meteorológico alto. Acionar pré-alerta, verificar disponibilidade de recursos."
        )
    else:
        level = "critical"
        recommendation = (
            "Risco crítico. Acionar equipes imediatamente. "
            "Condições extremamente favoráveis ao incêndio."
        )

    return score, level, factors, recommendation


async def get_weather_risk(lat: float, lng: float) -> WeatherRiskResponse:
    """Return weather-based fire risk for given coordinates.

    Caches results per rounded coordinate pair to avoid excessive API calls.
    Falls back to an 'unavailable' response on any error.
    """
    ttl_minutes = settings.external_api_cache_ttl_minutes
    cache_key = f"open_meteo:{_round_coord(lat)}:{_round_coord(lng)}"

    cached = cache_get(cache_key)
    if cached is not None:
        cached_response = WeatherRiskResponse.model_validate(cached)
        cached_response.source_status = "cached"
        return cached_response

    try:
        raw = await om_client.fetch_current_weather(lat, lng)
    except (httpx.HTTPError, Exception):
        resp = _UNAVAILABLE_RESPONSE_TEMPLATE.model_copy(
            update={"latitude": lat, "longitude": lng, "fetched_at": datetime.now(UTC).isoformat()}
        )
        return resp

    current = raw.get("current", {})
    temp = current.get("temperature_2m")
    humidity = current.get("relative_humidity_2m")
    wind_speed = current.get("wind_speed_10m")
    wind_direction = current.get("wind_direction_10m")
    precipitation = current.get("precipitation")

    score, level, factors, recommendation = _calculate_risk(
        temp, humidity, wind_speed, precipitation
    )

    now_str = datetime.now(UTC).isoformat()
    response = WeatherRiskResponse(
        source_status="live",
        latitude=lat,
        longitude=lng,
        temperature_c=temp,
        relative_humidity=humidity,
        wind_speed_kmh=wind_speed,
        wind_direction=wind_direction,
        precipitation_mm=precipitation,
        risk_level=level,  # type: ignore[arg-type]
        risk_score=score,
        factors=factors,
        recommendation=recommendation,
        fetched_at=now_str,
        cache_ttl_minutes=ttl_minutes,
    )

    cache_set(cache_key, response.model_dump(), ttl_minutes * 60)
    return response
