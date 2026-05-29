import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: str
    team_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str
    team_id: uuid.UUID | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    role: str | None = None
    team_id: uuid.UUID | None = None
    is_active: bool | None = None
    password: str | None = None
