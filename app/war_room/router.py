"""
War Room — alias de /api/v1/war-room para /api/v1/incidents/war-room.
Mantém compatibilidade com o frontend que referencia /war-room diretamente.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.database import get_db
from app.dependencies import require_role
from app.incidents import service as incident_service
from app.incidents.schemas import IncidentRead, WarRoomSummary

router = APIRouter(prefix="/api/v1/war-room", tags=["war-room"])


@router.get("", response_model=WarRoomSummary)
async def war_room(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> WarRoomSummary:
    return await incident_service.get_war_room(db)


@router.get("/{incident_id}", response_model=IncidentRead)
async def war_room_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
) -> IncidentRead:
    return await incident_service.get_incident(db, incident_id)
