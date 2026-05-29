import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.core.pagination import Page
from app.resources.model import Resource
from app.resources.schemas import ResourceCreate, ResourceRead, ResourceUpdate


async def list_resources(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    type: str | None = None,
    status: str | None = None,
) -> Page[ResourceRead]:
    offset = (page - 1) * size
    query = select(Resource)
    count_query = select(func.count()).select_from(Resource)

    if type is not None:
        query = query.where(Resource.type == type)
        count_query = count_query.where(Resource.type == type)
    if status is not None:
        query = query.where(Resource.status == status)
        count_query = count_query.where(Resource.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    result = await db.execute(
        query.order_by(Resource.created_at.desc()).offset(offset).limit(size)
    )
    resources = result.scalars().all()
    return Page.create(
        items=[ResourceRead.model_validate(r) for r in resources],
        total=total,
        page=page,
        size=size,
    )


async def get_resource(db: AsyncSession, resource_id: uuid.UUID) -> ResourceRead:
    result = await db.execute(select(Resource).where(Resource.id == resource_id))
    resource = result.scalar_one_or_none()
    if not resource:
        raise NotFoundException("Recurso")
    return ResourceRead.model_validate(resource)


async def create_resource(db: AsyncSession, data: ResourceCreate) -> ResourceRead:
    resource = Resource(
        name=data.name,
        type=data.type,
        status=data.status,
        quantity=data.quantity,
        location=data.location,
        assigned_incident_id=data.assigned_incident_id,
    )
    db.add(resource)
    await db.flush()
    return ResourceRead.model_validate(resource)


async def update_resource(
    db: AsyncSession,
    resource_id: uuid.UUID,
    data: ResourceUpdate,
) -> ResourceRead:
    result = await db.execute(select(Resource).where(Resource.id == resource_id))
    resource = result.scalar_one_or_none()
    if not resource:
        raise NotFoundException("Recurso")

    if data.name is not None:
        resource.name = data.name
    if data.type is not None:
        resource.type = data.type
    if data.status is not None:
        resource.status = data.status
    if data.quantity is not None:
        resource.quantity = data.quantity
    if data.location is not None:
        resource.location = data.location
    if data.assigned_incident_id is not None:
        resource.assigned_incident_id = data.assigned_incident_id

    resource.updated_at = datetime.now(UTC)
    await db.flush()
    return ResourceRead.model_validate(resource)
