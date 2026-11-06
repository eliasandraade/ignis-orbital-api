from uuid import UUID

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.exceptions import CredentialsException, ForbiddenException
from app.core.security import decode_token
from app.database import get_db

ROLE_LEVELS: dict[str, int] = {
    UserRole.PUBLICO: 0,
    UserRole.CAMPO: 1,
    UserRole.GESTOR: 2,
    UserRole.ORGAO: 3,
    UserRole.ADMIN: 4,
}

bearer_scheme = HTTPBearer()


# While an administrative reset is pending, the account can only read itself
# and choose a new password; every other endpoint answers 403.
PASSWORD_CHANGE_ALLOWED_PATHS = frozenset({"/api/v1/auth/me", "/api/v1/auth/change-password"})


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    from app.users.model import User

    try:
        payload = decode_token(credentials.credentials)
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise CredentialsException()
    except jwt.PyJWTError as exc:
        raise CredentialsException() from exc

    try:
        uid = UUID(user_id)
    except (ValueError, AttributeError) as exc:
        raise CredentialsException() from exc

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise CredentialsException()
    # Tokens issued before a role change, deactivation or reset are revoked.
    if int(payload.get("sv", 0)) != user.session_version:
        raise CredentialsException()
    if user.must_change_password and request.url.path not in PASSWORD_CHANGE_ALLOWED_PATHS:
        raise ForbiddenException("Troca de senha obrigatória antes de continuar")
    return user


def require_role(minimum_role: UserRole | str):
    min_level = ROLE_LEVELS.get(UserRole(minimum_role), 0)

    async def _check(current_user=Depends(get_current_user)):
        user_level = ROLE_LEVELS.get(UserRole(current_user.role), -1)
        if user_level < min_level:
            raise ForbiddenException(f"Perfil mínimo necessário: {minimum_role}")
        return current_user

    return _check
