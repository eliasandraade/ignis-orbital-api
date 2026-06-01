from typing import Literal

from pydantic import BaseModel


class WeatherRiskFactor(BaseModel):
    name: str
    impact: Literal["low", "moderate", "high"]
    description: str


class WeatherRiskResponse(BaseModel):
    source: str = "Open-Meteo"
    source_status: Literal["live", "cached", "unavailable"]
    latitude: float
    longitude: float
    temperature_c: float | None
    relative_humidity: float | None
    wind_speed_kmh: float | None
    wind_direction: float | None
    precipitation_mm: float | None
    risk_level: Literal["low", "moderate", "high", "critical"]
    risk_score: int
    factors: list[WeatherRiskFactor]
    recommendation: str
    fetched_at: str
    cache_ttl_minutes: int
