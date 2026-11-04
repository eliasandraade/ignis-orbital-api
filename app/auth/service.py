from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import CredentialsException, ForbiddenException
from app.core.security import create_access_token, hash_password, verify_password
from app.users.model import User
from app.users.schemas import UserRead

settings = get_settings()

# Verified when the e-mail does not exist, so an unknown account costs the same
# bcrypt time as a wrong password (no user enumeration by response time).
_DUMMY_HASH = hash_password("ignis-timing-equalizer-not-a-password")


def token_response(user: User) -> dict:
    token = create_access_token(
        subject=str(user.id), role=user.role, session_version=user.session_version
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.jwt_access_token_expire_minutes * 60,
        "user": UserRead.model_validate(user),
    }


async def login_user(db: AsyncSession, email: str, password: str) -> dict:
    user = await db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))
    if user is None:
        verify_password(password, _DUMMY_HASH)
        raise CredentialsException()
    # Same answer for a wrong password and an inactive account.
    if not verify_password(password, user.password_hash) or not user.is_active:
        raise CredentialsException()
    user.last_login_at = datetime.now(UTC)
    await db.flush()
    return token_response(user)


async def change_own_password(
    db: AsyncSession, user: User, current_password: str, new_password: str
) -> dict:
    if not verify_password(current_password, user.password_hash):
        raise ForbiddenException("Senha atual incorreta")
    if verify_password(new_password, user.password_hash):
        raise ForbiddenException("A nova senha deve ser diferente da atual")
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    # Every other session (other devices, a leaked token) ends here.
    user.session_version += 1
    user.row_version += 1
    user.updated_at = datetime.now(UTC).replace(tzinfo=None)
    await db.flush()
    return token_response(user)
