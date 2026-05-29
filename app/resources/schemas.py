import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import ResourceStatus, ResourceType


class ResourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    status: str
    quantity: int
    location: str | None = None
    assigned_incident_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class ResourceCreate(BaseModel):
    name: str
    type: ResourceType
    status: ResourceStatus = ResourceStatus.AVAILABLE
    quantity: int = 1
    location: str | None = None
    assigned_incident_id: uuid.UUID | None = None


class ResourceUpdate(BaseModel):
    name: str | None = None
    type: ResourceType | None = None
    status: ResourceStatus | None = None
    quantity: int | None = None
    location: str | None = None
    assigned_incident_id: uuid.UUID | None = None
