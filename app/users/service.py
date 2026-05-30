import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.core.pagination import Page
from app.core.security import hash_password
from app.users.model import User
from app.users.schemas import UserCreate, UserRead, UserUpdate


async def list_users(db: AsyncSession, page: int = 1, size: int = 20) -> Page[UserRead]:
    offset = (page - 1) * size
    total_result = await db.execute(select(func.count()).select_from(User))
    total = total_result.scalar_one()
    result = await db.execute(
        select(User).offset(offset).limit(size).order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return Page.create(
        items=[UserRead.model_validate(u) for u in users],
        total=total,
        page=page,
        size=size,
    )


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> UserRead:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("Usuário")
    return UserRead.model_validate(user)


async def create_user(db: AsyncSession, data: UserCreate) -> UserRead:
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise ConflictException("Email já cadastrado")
    user = User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
        team_id=data.team_id,
    )
    db.add(user)
    await db.flush()
    return UserRead.model_validate(user)


async def delete_user(db: AsyncSession, user_id: uuid.UUID) -> UserRead:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("Usuário")
    user.is_active = False
    user.updated_at = datetime.now(UTC).replace(tzinfo=None)
    await db.flush()
    return UserRead.model_validate(user)


async def update_user(db: AsyncSession, user_id: uuid.UUID, data: UserUpdate) -> UserRead:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundException("Usuário")
    if data.name is not None:
        user.name = data.name
    if data.email is not None:
        user.email = data.email
    if data.role is not None:
        user.role = data.role
    if data.team_id is not None:
        user.team_id = data.team_id
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.password is not None:
        user.password_hash = hash_password(data.password)
    user.updated_at = datetime.now(UTC).replace(tzinfo=None)
    await db.flush()
    return UserRead.model_validate(user)
