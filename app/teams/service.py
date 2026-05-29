import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.core.pagination import Page
from app.teams.model import FieldTeam
from app.teams.schemas import FieldTeamCreate, FieldTeamRead, FieldTeamUpdate


async def list_teams(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    status: str | None = None,
) -> Page[FieldTeamRead]:
    offset = (page - 1) * size
    query = select(FieldTeam)
    count_query = select(func.count()).select_from(FieldTeam)

    if status is not None:
        query = query.where(FieldTeam.status == status)
        count_query = count_query.where(FieldTeam.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    result = await db.execute(
        query.order_by(FieldTeam.created_at.desc()).offset(offset).limit(size)
    )
    teams = result.scalars().all()
    return Page.create(
        items=[FieldTeamRead.model_validate(t) for t in teams],
        total=total,
        page=page,
        size=size,
    )


async def get_team(db: AsyncSession, team_id: uuid.UUID) -> FieldTeamRead:
    result = await db.execute(select(FieldTeam).where(FieldTeam.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise NotFoundException("Equipe")
    return FieldTeamRead.model_validate(team)


async def create_team(db: AsyncSession, data: FieldTeamCreate) -> FieldTeamRead:
    team = FieldTeam(
        name=data.name,
        type=data.type,
        status=data.status,
        current_latitude=data.current_latitude,
        current_longitude=data.current_longitude,
        notes=data.notes,
    )
    db.add(team)
    await db.flush()
    return FieldTeamRead.model_validate(team)


async def update_team(
    db: AsyncSession,
    team_id: uuid.UUID,
    data: FieldTeamUpdate,
) -> FieldTeamRead:
    result = await db.execute(select(FieldTeam).where(FieldTeam.id == team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise NotFoundException("Equipe")

    if data.name is not None:
        team.name = data.name
    if data.type is not None:
        team.type = data.type
    if data.status is not None:
        team.status = data.status
    if data.current_latitude is not None:
        team.current_latitude = data.current_latitude
    if data.current_longitude is not None:
        team.current_longitude = data.current_longitude
    if data.notes is not None:
        team.notes = data.notes

    team.updated_at = datetime.now(UTC)
    await db.flush()
    return FieldTeamRead.model_validate(team)
