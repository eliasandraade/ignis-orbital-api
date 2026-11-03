import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.enums import UserRole
from app.core.passwords import validate_new_password


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
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str
    # Validated against the enum: an unknown role used to be stored and then
    # broke every authorization check for that user.
    role: UserRole
    team_id: uuid.UUID | None = None

    _check_password = field_validator("password")(validate_new_password)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=255)
    email: EmailStr | None = None
    role: UserRole | None = None
    team_id: uuid.UUID | None = None
    is_active: bool | None = None
    password: str | None = None

    @field_validator("password")
    @classmethod
    def _check_password(cls, v: str | None) -> str | None:
        return None if v is None else validate_new_password(v)
