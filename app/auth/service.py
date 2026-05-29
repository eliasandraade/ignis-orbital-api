from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import CredentialsException
from app.core.security import create_access_token, verify_password
from app.users.model import User
from app.users.schemas import UserRead

settings = get_settings()


async def login_user(db: AsyncSession, email: str, password: str) -> dict:
    result = await db.execute(select(User).where(User.email == email, User.is_active == True))  # noqa: E712
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        raise CredentialsException()
    token = create_access_token(subject=str(user.id), role=user.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
        "user": UserRead.model_validate(user),
    }
