import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_action
from app.core.enums import UserRole
from app.core.pagination import Page
from app.database import get_db
from app.dependencies import require_role
from app.users import service as user_service
from app.users.schemas import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/api/v1/admin/users", tags=["admin"])


@router.get("", response_model=Page[UserRead])
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.ADMIN)),
):
    return await user_service.list_users(db, page, size)


@router.post("", response_model=UserRead, status_code=201)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.ADMIN)),
):
    user = await user_service.create_user(db, body)
    await log_action(
        db,
        "user.created",
        "User",
        str(user.id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.ADMIN)),
):
    user = await user_service.update_user(db, user_id, body)
    await log_action(
        db,
        "user.updated",
        "User",
        str(user_id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return user
