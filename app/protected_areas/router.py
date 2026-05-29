import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_action
from app.core.enums import UserRole
from app.core.pagination import Page
from app.database import get_db
from app.dependencies import require_role
from app.protected_areas import service as area_service
from app.protected_areas.schemas import ProtectedAreaCreate, ProtectedAreaRead, ProtectedAreaUpdate

router = APIRouter(prefix="/api/v1/protected-areas", tags=["protected-areas"])


@router.get("", response_model=Page[ProtectedAreaRead])
async def list_areas(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    state: str | None = Query(None, description="Filtrar por UF (2 letras)"),
    db: AsyncSession = Depends(get_db),
):
    return await area_service.list_areas(db, page, size, state)


@router.get("/{area_id}", response_model=ProtectedAreaRead)
async def get_area(
    area_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    return await area_service.get_area(db, area_id)


@router.post("", response_model=ProtectedAreaRead, status_code=status.HTTP_201_CREATED)
async def create_area(
    body: ProtectedAreaCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.ORGAO)),
):
    area = await area_service.create_area(db, body)
    await log_action(
        db,
        "area.created",
        "ProtectedArea",
        str(area.id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return area


@router.patch("/{area_id}", response_model=ProtectedAreaRead)
async def update_area(
    area_id: uuid.UUID,
    body: ProtectedAreaUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.ORGAO)),
):
    area = await area_service.update_area(db, area_id, body)
    await log_action(
        db,
        "area.updated",
        "ProtectedArea",
        str(area_id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return area


@router.delete("/{area_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_area(
    area_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.ADMIN)),
):
    await area_service.delete_area(db, area_id)
    await log_action(
        db,
        "area.deleted",
        "ProtectedArea",
        str(area_id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
