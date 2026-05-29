import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.enums import IncidentSeverity, IncidentSource, IncidentStatus, IncidentType


class IncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    title: str
    type: str
    severity: str
    status: str
    protected_area_id: uuid.UUID | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_wkt: str | None = None
    source: str
    confidence: float
    affected_hectares: float | None = None
    wind_direction: str | None = None
    wind_speed: float | None = None
    humidity: float | None = None
    temperature: float | None = None
    detected_at: datetime
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def convert_geometry(cls, v: Any) -> Any:
        try:
            from geoalchemy2.shape import to_shape
            from geoalchemy2.types import WKBElement
        except ImportError:
            return v

        if hasattr(v, "__dict__"):
            data = {k: val for k, val in vars(v).items() if not k.startswith("_")}
        elif isinstance(v, dict):
            data = dict(v)
        else:
            return v

        loc = data.get("location")
        if isinstance(loc, WKBElement):
            data["location_wkt"] = to_shape(loc).wkt
        else:
            data["location_wkt"] = None
        data.pop("location", None)

        return data


class IncidentCreate(BaseModel):
    title: str
    type: IncidentType
    severity: IncidentSeverity
    protected_area_id: uuid.UUID
    latitude: float
    longitude: float
    source: IncidentSource = IncidentSource.REPORT
    confidence: float = 0.8
    detected_at: datetime
    affected_hectares: float | None = None
    wind_direction: str | None = None
    wind_speed: float | None = None
    humidity: float | None = None
    temperature: float | None = None


class IncidentUpdate(BaseModel):
    title: str | None = None
    type: IncidentType | None = None
    severity: IncidentSeverity | None = None
    protected_area_id: uuid.UUID | None = None
    latitude: float | None = None
    longitude: float | None = None
    source: IncidentSource | None = None
    confidence: float | None = None
    detected_at: datetime | None = None
    affected_hectares: float | None = None
    wind_direction: str | None = None
    wind_speed: float | None = None
    humidity: float | None = None
    temperature: float | None = None


class IncidentStatusUpdate(BaseModel):
    status: IncidentStatus
    reason: str


class IncidentEventCreate(BaseModel):
    type: str
    description: str
    timestamp: datetime | None = None


class IncidentEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    type: str
    actor_id: uuid.UUID | None = None
    actor_name: str
    description: str
    timestamp: datetime


class WarRoomSummary(BaseModel):
    active_incidents: list[IncidentRead]
    total_active: int
    by_severity: dict[str, int]
    latest_events: list[IncidentEventRead]
