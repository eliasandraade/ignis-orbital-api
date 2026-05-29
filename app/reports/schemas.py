import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.enums import ReportStatus, ReportType, ReportUrgency


class ReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    protocol: str
    type: str
    description: str
    urgency: str
    status: str
    reporter_name: str | None = None
    contact: str | None = None
    is_anonymous: bool
    latitude: float
    longitude: float
    location_wkt: str | None = None
    protected_area_id: uuid.UUID | None = None
    evidence_urls: list[str] | None = None
    validation_notes: str | None = None
    linked_incident_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def convert_location(cls, v: Any) -> Any:
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


class ReportStatusPublic(BaseModel):
    """Schema seguro para consulta pública por protocolo — não expõe dados pessoais."""

    model_config = ConfigDict(from_attributes=True)

    protocol: str
    type: str
    urgency: str
    status: str
    is_anonymous: bool
    protected_area_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class ReportCreate(BaseModel):
    type: ReportType
    description: str
    urgency: ReportUrgency
    latitude: float
    longitude: float
    reporter_name: str | None = None
    contact: str | None = None
    is_anonymous: bool = False
    evidence_urls: list[str] = []
    protected_area_id: uuid.UUID | None = None


class ReportStatusUpdate(BaseModel):
    status: ReportStatus
    validation_notes: str | None = None
