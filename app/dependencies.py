from uuid import UUID

import jwt
from fastapi import Depends
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


async def get_current_user(
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
    return user


def require_role(minimum_role: UserRole | str):
    min_level = ROLE_LEVELS.get(UserRole(minimum_role), 0)

    async def _check(current_user=Depends(get_current_user)):
        user_level = ROLE_LEVELS.get(UserRole(current_user.role), -1)
        if user_level < min_level:
            raise ForbiddenException(f"Perfil mínimo necessário: {minimum_role}")
        return current_user

    return _check
