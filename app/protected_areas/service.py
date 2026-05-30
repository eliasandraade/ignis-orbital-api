import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.core.pagination import Page
from app.protected_areas.model import ProtectedArea
from app.protected_areas.schemas import (
    ProtectedAreaCreate,
    ProtectedAreaRead,
    ProtectedAreaUpdate,
)


async def list_areas(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    state: str | None = None,
) -> Page[ProtectedAreaRead]:
    offset = (page - 1) * size
    query = select(ProtectedArea)
    count_query = select(func.count()).select_from(ProtectedArea)
    if state:
        query = query.where(ProtectedArea.state == state.upper())
        count_query = count_query.where(ProtectedArea.state == state.upper())

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    result = await db.execute(query.order_by(ProtectedArea.name).offset(offset).limit(size))
    areas = result.scalars().all()
    return Page.create(
        items=[ProtectedAreaRead.model_validate(a) for a in areas],
        total=total,
        page=page,
        size=size,
    )


async def get_area(db: AsyncSession, area_id: uuid.UUID) -> ProtectedAreaRead:
    result = await db.execute(select(ProtectedArea).where(ProtectedArea.id == area_id))
    area = result.scalar_one_or_none()
    if not area:
        raise NotFoundException("Área protegida")
    return ProtectedAreaRead.model_validate(area)


async def create_area(db: AsyncSession, data: ProtectedAreaCreate) -> ProtectedAreaRead:
    area = ProtectedArea(
        name=data.name,
        category=data.category,
        municipality=data.municipality,
        state=data.state.upper(),
        organ=data.organ,
        area_ha=data.area_ha,
        center_lat=data.center_lat,
        center_lng=data.center_lng,
        geometry=data.geometry_wkt,
        buffer_zone=data.buffer_zone_wkt,
        source=data.source,
        data_quality=data.data_quality,
        confidence=data.confidence,
    )
    db.add(area)
    await db.flush()
    return ProtectedAreaRead.model_validate(area)


async def update_area(
    db: AsyncSession,
    area_id: uuid.UUID,
    data: ProtectedAreaUpdate,
) -> ProtectedAreaRead:
    result = await db.execute(select(ProtectedArea).where(ProtectedArea.id == area_id))
    area = result.scalar_one_or_none()
    if not area:
        raise NotFoundException("Área protegida")

    if data.name is not None:
        area.name = data.name
    if data.category is not None:
        area.category = data.category
    if data.municipality is not None:
        area.municipality = data.municipality
    if data.state is not None:
        area.state = data.state.upper()
    if data.organ is not None:
        area.organ = data.organ
    if data.area_ha is not None:
        area.area_ha = data.area_ha
    if data.center_lat is not None:
        area.center_lat = data.center_lat
    if data.center_lng is not None:
        area.center_lng = data.center_lng
    if data.geometry_wkt is not None:
        area.geometry = data.geometry_wkt
    if data.buffer_zone_wkt is not None:
        area.buffer_zone = data.buffer_zone_wkt
    if data.source is not None:
        area.source = data.source
    if data.data_quality is not None:
        area.data_quality = data.data_quality
    if data.confidence is not None:
        area.confidence = data.confidence

    area.updated_at = datetime.now(UTC).replace(tzinfo=None)
    await db.flush()
    return ProtectedAreaRead.model_validate(area)


async def delete_area(db: AsyncSession, area_id: uuid.UUID) -> None:
    result = await db.execute(select(ProtectedArea).where(ProtectedArea.id == area_id))
    area = result.scalar_one_or_none()
    if not area:
        raise NotFoundException("Área protegida")
    await db.delete(area)
    await db.flush()
