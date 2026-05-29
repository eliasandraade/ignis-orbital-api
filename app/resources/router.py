import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_action
from app.core.enums import ResourceStatus, ResourceType, UserRole
from app.core.pagination import Page
from app.database import get_db
from app.dependencies import require_role
from app.resources import service as resources_service
from app.resources.schemas import ResourceCreate, ResourceRead, ResourceUpdate

router = APIRouter(prefix="/api/v1/resources", tags=["resources"])


@router.get("", response_model=Page[ResourceRead])
async def list_resources(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    type: ResourceType | None = Query(None),
    status: ResourceStatus | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> Page[ResourceRead]:
    return await resources_service.list_resources(db, page, size, type, status)


@router.get("/{resource_id}", response_model=ResourceRead)
async def get_resource(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> ResourceRead:
    return await resources_service.get_resource(db, resource_id)


@router.post("", response_model=ResourceRead, status_code=status.HTTP_201_CREATED)
async def create_resource(
    body: ResourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.ADMIN)),
) -> ResourceRead:
    resource = await resources_service.create_resource(db, body)
    await log_action(
        db,
        "resource.created",
        "Resource",
        str(resource.id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return resource


@router.patch("/{resource_id}", response_model=ResourceRead)
async def update_resource(
    resource_id: uuid.UUID,
    body: ResourceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> ResourceRead:
    resource = await resources_service.update_resource(db, resource_id, body)
    await log_action(
        db,
        "resource.updated",
        "Resource",
        str(resource_id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return resource
