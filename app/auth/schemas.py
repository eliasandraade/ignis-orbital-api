from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.passwords import validate_new_password
from app.users.schemas import UserRead


class LoginRequest(BaseModel):
    email: str = Field(max_length=255, examples=["admin@orgao.example"])
    password: str = Field(max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(max_length=256)
    new_password: str

    _check_new = field_validator("new_password")(validate_new_password)
