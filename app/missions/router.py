import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_action
from app.core.enums import MissionStatus, UserRole
from app.core.pagination import Page
from app.database import get_db
from app.dependencies import require_role
from app.missions import service as missions_service
from app.missions.schemas import MissionCreate, MissionRead, MissionStatusUpdate, MissionUpdate

router = APIRouter(prefix="/api/v1/missions", tags=["missions"])


@router.get("", response_model=Page[MissionRead])
async def list_missions(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    incident_id: uuid.UUID | None = Query(None),
    status: MissionStatus | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> Page[MissionRead]:
    return await missions_service.list_missions(db, page, size, incident_id, status)


@router.get("/{mission_id}", response_model=MissionRead)
async def get_mission(
    mission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> MissionRead:
    return await missions_service.get_mission(db, mission_id)


@router.post("", response_model=MissionRead, status_code=status.HTTP_201_CREATED)
async def create_mission(
    body: MissionCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> MissionRead:
    mission = await missions_service.create_mission(db, body, current_user)
    await log_action(
        db,
        "mission.created",
        "Mission",
        str(mission.id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return mission


@router.patch("/{mission_id}", response_model=MissionRead)
async def update_mission(
    mission_id: uuid.UUID,
    body: MissionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> MissionRead:
    mission = await missions_service.update_mission(db, mission_id, body)
    await log_action(
        db,
        "mission.updated",
        "Mission",
        str(mission_id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return mission


@router.patch("/{mission_id}/status", response_model=MissionRead)
async def update_mission_status(
    mission_id: uuid.UUID,
    body: MissionStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> MissionRead:
    mission = await missions_service.update_mission_status(db, mission_id, body, current_user)
    await log_action(
        db,
        "mission.status_changed",
        "Mission",
        str(mission_id),
        actor_name=current_user.name,
        actor_id=current_user.id,
        metadata={"new_status": body.status},
    )
    await db.commit()
    return mission
