import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_action
from app.core.enums import IncidentSeverity, IncidentSource, IncidentStatus, IncidentType, UserRole
from app.core.pagination import Page
from app.database import get_db
from app.dependencies import require_role
from app.incidents import service as incident_service
from app.incidents.schemas import (
    IncidentCreate,
    IncidentEventCreate,
    IncidentEventRead,
    IncidentRead,
    IncidentStatusUpdate,
    IncidentUpdate,
    WarRoomSummary,
)

router = APIRouter(prefix="/api/v1/incidents", tags=["incidents"])


@router.get("", response_model=Page[IncidentRead])
async def list_incidents(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    type: IncidentType | None = Query(None),
    severity: IncidentSeverity | None = Query(None),
    status: IncidentStatus | None = Query(None),
    area_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> Page[IncidentRead]:
    return await incident_service.list_incidents(db, page, size, type, severity, status, area_id)


# IMPORTANT: static routes must be registered BEFORE /{incident_id}
@router.get("/war-room", response_model=WarRoomSummary)
async def get_war_room(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> WarRoomSummary:
    return await incident_service.get_war_room(db)


@router.get(
    "/active/critical",
    response_model=Page[IncidentRead],
    summary="Incidentes ativos críticos",
    description="Atalho: lista incidentes com status=active e severity=critical.",
)
async def list_active_critical(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> Page[IncidentRead]:
    return await incident_service.list_incidents(
        db, page, size,
        status=IncidentStatus.ACTIVE,
        severity=IncidentSeverity.CRITICAL,
    )


@router.get("/{incident_id}", response_model=IncidentRead)
async def get_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> IncidentRead:
    return await incident_service.get_incident(db, incident_id)


@router.post("", response_model=IncidentRead, status_code=status.HTTP_201_CREATED)
async def create_incident(
    body: IncidentCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> IncidentRead:
    incident = await incident_service.create_incident(db, body, current_user)
    await log_action(
        db,
        "incident.created",
        "Incident",
        str(incident.id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return incident


@router.patch("/{incident_id}", response_model=IncidentRead)
async def update_incident(
    incident_id: uuid.UUID,
    body: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> IncidentRead:
    incident = await incident_service.update_incident(db, incident_id, body)
    await db.commit()
    return incident


@router.patch("/{incident_id}/status", response_model=IncidentRead)
async def update_incident_status(
    incident_id: uuid.UUID,
    body: IncidentStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> IncidentRead:
    incident = await incident_service.update_incident_status(db, incident_id, body, current_user)
    await log_action(
        db,
        "incident.status_changed",
        "Incident",
        str(incident_id),
        actor_name=current_user.name,
        actor_id=current_user.id,
        metadata={"new_status": body.status},
    )
    await db.commit()
    return incident


@router.post("/{incident_id}/activate-protocol", response_model=IncidentRead)
async def activate_protocol(
    incident_id: uuid.UUID,
    reason: str = "Protocolo de emergência ativado",
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> IncidentRead:
    body = IncidentStatusUpdate(status=IncidentStatus.PROTOCOL_ACTIVATED, reason=reason)
    incident = await incident_service.update_incident_status(db, incident_id, body, current_user)
    await log_action(
        db,
        "incident.protocol_activated",
        "Incident",
        str(incident_id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return incident


@router.get("/{incident_id}/timeline", response_model=list[IncidentEventRead])
async def get_incident_timeline(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> list[IncidentEventRead]:
    return await incident_service.get_incident_timeline(db, incident_id)


@router.post(
    "/{incident_id}/events",
    response_model=IncidentEventRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_incident_event(
    incident_id: uuid.UUID,
    body: IncidentEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> IncidentEventRead:
    event = await incident_service.add_incident_event(db, incident_id, body, current_user)
    await db.commit()
    return event


# Expose source type for OpenAPI completeness
__all__ = [
    "router",
    "IncidentSource",
]
