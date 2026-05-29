import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.enums import EvidenceType


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID | None = None
    report_id: uuid.UUID | None = None
    type: str
    url: str
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_wkt: str | None = None
    source: str | None = None
    created_at: datetime

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


class EvidenceCreate(BaseModel):
    incident_id: uuid.UUID | None = None
    report_id: uuid.UUID | None = None
    type: EvidenceType
    url: str
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    source: str | None = None
