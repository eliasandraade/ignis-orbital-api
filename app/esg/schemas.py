import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ESGReportCreate(BaseModel):
    protected_area_id: uuid.UUID | None = None
    period_start: datetime
    period_end: datetime
    monitored_area_ha: float = 0.0
    incidents_resolved: int = 0
    average_response_minutes: float = 0.0
    heat_spots_detected: int = 0
    vegetation_loss_estimated_ha: float = 0.0
    prevented_impact_estimate: str | None = None
    ods: dict[str, bool] | None = None


class ESGReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    protected_area_id: uuid.UUID | None
    period_start: datetime
    period_end: datetime
    monitored_area_ha: float
    incidents_resolved: int
    average_response_minutes: float
    heat_spots_detected: int
    vegetation_loss_estimated_ha: float
    prevented_impact_estimate: str | None
    ods: dict[str, bool] | None
    created_at: datetime
