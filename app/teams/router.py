import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_action
from app.core.enums import TeamStatus, UserRole
from app.core.pagination import Page
from app.database import get_db
from app.dependencies import require_role
from app.teams import service as teams_service
from app.teams.schemas import FieldTeamCreate, FieldTeamRead, FieldTeamUpdate

router = APIRouter(prefix="/api/v1/teams", tags=["teams"])


@router.get("", response_model=Page[FieldTeamRead])
async def list_teams(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: TeamStatus | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> Page[FieldTeamRead]:
    return await teams_service.list_teams(db, page, size, status)


@router.get("/{team_id}", response_model=FieldTeamRead)
async def get_team(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> FieldTeamRead:
    return await teams_service.get_team(db, team_id)


@router.post("", response_model=FieldTeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: FieldTeamCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.ADMIN)),
) -> FieldTeamRead:
    team = await teams_service.create_team(db, body)
    await log_action(
        db,
        "team.created",
        "FieldTeam",
        str(team.id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return team


@router.patch("/{team_id}", response_model=FieldTeamRead)
async def update_team(
    team_id: uuid.UUID,
    body: FieldTeamUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> FieldTeamRead:
    team = await teams_service.update_team(db, team_id, body)
    await log_action(
        db,
        "team.updated",
        "FieldTeam",
        str(team_id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return team
