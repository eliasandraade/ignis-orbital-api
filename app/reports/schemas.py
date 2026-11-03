import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

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
    latitude: float | None = None
    longitude: float | None = None
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
    """Public, unauthenticated input — every field is bounded."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    type: ReportType
    description: str = Field(min_length=10, max_length=4000)
    urgency: ReportUrgency
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    reporter_name: str | None = Field(default=None, max_length=255)
    contact: str | None = Field(default=None, max_length=255)
    is_anonymous: bool = False
    evidence_urls: list[HttpUrl] = Field(default_factory=list, max_length=10)
    protected_area_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def enforce_anonymity(self) -> "ReportCreate":
        # An anonymous report must not store identifying data.
        if self.is_anonymous:
            self.reporter_name = None
            self.contact = None
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude e longitude devem ser informadas juntas")
        return self

    @property
    def evidence_url_strings(self) -> list[str]:
        return [str(u) for u in self.evidence_urls]


class ReportStatusUpdate(BaseModel):
    status: ReportStatus
    validation_notes: str | None = None
