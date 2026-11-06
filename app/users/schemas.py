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
    # The client must route the user to the password change screen.
    must_change_password: bool = False


class UserAdminRead(UserRead):
    """What an administrator sees. Never includes the password or its hash."""

    last_login_at: datetime | None = None  # null: no login recorded since tracking began
    row_version: int = Field(description="Envie em expected_version para editar (409 se mudou)")


class UserCreate(BaseModel):
    """Used by the bootstrap and validation tooling (kept for compatibility)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str
    # Validated against the enum: an unknown role used to be stored and then
    # broke every authorization check for that user.
    role: UserRole
    team_id: uuid.UUID | None = None

    _check_password = field_validator("password")(validate_new_password)


class _Reason(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=5, max_length=500, description="Motivo, registrado na auditoria")


class _Guarded(_Reason):
    expected_version: int = Field(ge=1, description="row_version lido antes da edição")
    confirm_password: str = Field(
        min_length=1, max_length=256, description="Senha do administrador que executa a ação"
    )


class AdminUserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=255, examples=["Maria Souza"])
    email: EmailStr = Field(examples=["maria.souza@orgao.example"])
    role: UserRole
    team_id: uuid.UUID | None = None
    temporary_password: str = Field(
        description="Senha provisória, comunicada fora do sistema; a troca é exigida no 1º login"
    )
    reason: str | None = Field(default=None, max_length=500)

    _check_password = field_validator("temporary_password")(validate_new_password)


class AdminUserProfileUpdate(BaseModel):
    """Name, e-mail and team only. Role, status and password have their own actions."""

    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=2, max_length=255)
    email: EmailStr | None = None
    team_id: uuid.UUID | None = Field(default=None, description="null remove a equipe")


class AdminRoleChange(_Guarded):
    role: UserRole


class AdminStatusChange(_Guarded):
    pass


class AdminPasswordReset(_Guarded):
    temporary_password: str

    _check_password = field_validator("temporary_password")(validate_new_password)
