from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class OrbitalAlert(BaseModel):
    id: str
    type: Literal["heat_spot", "burn_confirmed", "deforestation", "anomaly"]
    lat: float
    lng: float
    area_id: str | None
    confidence: int
    source: str
    detected_at: datetime
    fetched_at: datetime
    converted_to_incident_id: str | None = None
    raw_data: dict | None = None


class OrbitalAlertListResponse(BaseModel):
    items: list[OrbitalAlert]
    total: int
    source_status: Literal["live", "cached", "disabled_missing_api_key", "unavailable"]
    since: str | None = None
    cached_at: str | None = None


class IngestResponse(BaseModel):
    status: Literal["ok", "partial", "disabled_missing_api_key", "error"]
    message: str
    records_fetched: int = 0
    records_inserted: int = 0
    records_skipped: int = 0


class ConvertToIncidentRequest(BaseModel):
    priority: Literal["alta", "media", "baixa"] = "media"
    notes: str = ""


class ConvertToIncidentResponse(BaseModel):
    incident_id: str
    orbital_alert_id: str
