import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import MissionStatus


class MissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    incident_id: uuid.UUID
    team_id: uuid.UUID
    status: str
    objective: str
    notes: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class MissionCreate(BaseModel):
    incident_id: uuid.UUID
    team_id: uuid.UUID
    objective: str
    notes: str | None = None
    started_at: datetime | None = None


class MissionUpdate(BaseModel):
    incident_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    objective: str | None = None
    notes: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class MissionStatusUpdate(BaseModel):
    status: MissionStatus
    notes: str | None = None
