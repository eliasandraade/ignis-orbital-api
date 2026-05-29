import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import TeamStatus, TeamType


class FieldTeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    status: str
    current_latitude: float | None = None
    current_longitude: float | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class FieldTeamCreate(BaseModel):
    name: str
    type: TeamType
    status: TeamStatus = TeamStatus.AVAILABLE
    current_latitude: float | None = None
    current_longitude: float | None = None
    notes: str | None = None


class FieldTeamUpdate(BaseModel):
    name: str | None = None
    type: TeamType | None = None
    status: TeamStatus | None = None
    current_latitude: float | None = None
    current_longitude: float | None = None
    notes: str | None = None
