import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.enums import DataQuality, ProtectedAreaCategory


class ProtectedAreaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: str
    municipality: str
    state: str
    organ: str
    area_ha: float
    source: str
    data_quality: str
    confidence: float
    center_lat: float
    center_lng: float
    geometry_wkt: str | None = None
    buffer_zone_wkt: str | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def convert_geometries(cls, v: Any) -> Any:
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

        geom = data.get("geometry")
        if isinstance(geom, WKBElement):
            data["geometry_wkt"] = to_shape(geom).wkt
        else:
            data["geometry_wkt"] = None
        data.pop("geometry", None)

        buf = data.get("buffer_zone")
        if isinstance(buf, WKBElement):
            data["buffer_zone_wkt"] = to_shape(buf).wkt
        else:
            data["buffer_zone_wkt"] = None
        data.pop("buffer_zone", None)

        return data


class ProtectedAreaCreate(BaseModel):
    name: str
    category: ProtectedAreaCategory
    municipality: str
    state: str
    organ: str
    area_ha: float
    center_lat: float
    center_lng: float
    geometry_wkt: str | None = None
    buffer_zone_wkt: str | None = None
    source: str = "base demonstrativa acadêmica"
    data_quality: DataQuality = DataQuality.ESTIMATED
    confidence: float = 0.5


class ProtectedAreaUpdate(BaseModel):
    name: str | None = None
    category: ProtectedAreaCategory | None = None
    municipality: str | None = None
    state: str | None = None
    organ: str | None = None
    area_ha: float | None = None
    center_lat: float | None = None
    center_lng: float | None = None
    geometry_wkt: str | None = None
    buffer_zone_wkt: str | None = None
    source: str | None = None
    data_quality: DataQuality | None = None
    confidence: float | None = None
