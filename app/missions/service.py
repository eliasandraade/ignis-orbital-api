import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MissionStatus
from app.core.exceptions import NotFoundException
from app.core.pagination import Page
from app.missions.model import Mission
from app.missions.schemas import MissionCreate, MissionRead, MissionStatusUpdate, MissionUpdate


async def list_missions(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    incident_id: uuid.UUID | None = None,
    status: str | None = None,
) -> Page[MissionRead]:
    offset = (page - 1) * size
    query = select(Mission)
    count_query = select(func.count()).select_from(Mission)

    if incident_id is not None:
        query = query.where(Mission.incident_id == incident_id)
        count_query = count_query.where(Mission.incident_id == incident_id)
    if status is not None:
        query = query.where(Mission.status == status)
        count_query = count_query.where(Mission.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    result = await db.execute(
        query.order_by(Mission.created_at.desc()).offset(offset).limit(size)
    )
    missions = result.scalars().all()
    return Page.create(
        items=[MissionRead.model_validate(m) for m in missions],
        total=total,
        page=page,
        size=size,
    )


async def get_mission(db: AsyncSession, mission_id: uuid.UUID) -> MissionRead:
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = result.scalar_one_or_none()
    if not mission:
        raise NotFoundException("Missão")
    return MissionRead.model_validate(mission)


async def create_mission(
    db: AsyncSession,
    data: MissionCreate,
    actor: object,
) -> MissionRead:
    mission = Mission(
        incident_id=data.incident_id,
        team_id=data.team_id,
        status=MissionStatus.PLANNED,
        objective=data.objective,
        notes=data.notes,
        started_at=data.started_at,
    )
    db.add(mission)
    await db.flush()
    return MissionRead.model_validate(mission)


async def update_mission(
    db: AsyncSession,
    mission_id: uuid.UUID,
    data: MissionUpdate,
) -> MissionRead:
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = result.scalar_one_or_none()
    if not mission:
        raise NotFoundException("Missão")

    if data.incident_id is not None:
        mission.incident_id = data.incident_id
    if data.team_id is not None:
        mission.team_id = data.team_id
    if data.objective is not None:
        mission.objective = data.objective
    if data.notes is not None:
        mission.notes = data.notes
    if data.started_at is not None:
        mission.started_at = data.started_at
    if data.completed_at is not None:
        mission.completed_at = data.completed_at

    mission.updated_at = datetime.now(UTC).replace(tzinfo=None)
    await db.flush()
    return MissionRead.model_validate(mission)


async def update_mission_status(
    db: AsyncSession,
    mission_id: uuid.UUID,
    data: MissionStatusUpdate,
    actor: object,
) -> MissionRead:
    result = await db.execute(select(Mission).where(Mission.id == mission_id))
    mission = result.scalar_one_or_none()
    if not mission:
        raise NotFoundException("Missão")

    mission.status = data.status
    if data.notes is not None:
        mission.notes = data.notes

    now = datetime.now(UTC).replace(tzinfo=None)
    if data.status == MissionStatus.ACTIVE and mission.started_at is None:
        mission.started_at = now
    if data.status in (MissionStatus.COMPLETED, MissionStatus.ABORTED):
        mission.completed_at = now

    mission.updated_at = now
    await db.flush()
    return MissionRead.model_validate(mission)
