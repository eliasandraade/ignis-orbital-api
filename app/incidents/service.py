import random
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import IncidentStatus
from app.core.exceptions import NotFoundException
from app.core.pagination import Page
from app.incidents.model import Incident, IncidentEvent
from app.incidents.schemas import (
    IncidentCreate,
    IncidentEventCreate,
    IncidentEventRead,
    IncidentRead,
    IncidentStatusUpdate,
    IncidentUpdate,
    WarRoomSummary,
)


def _generate_code() -> str:
    return f"IGN-CE-2026-{random.randint(0, 9999):04d}"


async def list_incidents(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    type: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    area_id: uuid.UUID | None = None,
) -> Page[IncidentRead]:
    from sqlalchemy import func

    offset = (page - 1) * size
    query = select(Incident)
    count_query = select(func.count()).select_from(Incident)

    if type is not None:
        query = query.where(Incident.type == type)
        count_query = count_query.where(Incident.type == type)
    if severity is not None:
        query = query.where(Incident.severity == severity)
        count_query = count_query.where(Incident.severity == severity)
    if status is not None:
        query = query.where(Incident.status == status)
        count_query = count_query.where(Incident.status == status)
    if area_id is not None:
        query = query.where(Incident.protected_area_id == area_id)
        count_query = count_query.where(Incident.protected_area_id == area_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    result = await db.execute(
        query.order_by(Incident.created_at.desc()).offset(offset).limit(size)
    )
    incidents = result.scalars().all()
    return Page.create(
        items=[IncidentRead.model_validate(i) for i in incidents],
        total=total,
        page=page,
        size=size,
    )


async def get_incident(db: AsyncSession, incident_id: uuid.UUID) -> IncidentRead:
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise NotFoundException("Incidente")
    return IncidentRead.model_validate(incident)


async def create_incident(
    db: AsyncSession,
    data: IncidentCreate,
    actor: object,
) -> IncidentRead:
    incident = Incident(
        code=_generate_code(),
        title=data.title,
        type=data.type,
        severity=data.severity,
        status=IncidentStatus.DETECTED,
        protected_area_id=data.protected_area_id,
        latitude=data.latitude,
        longitude=data.longitude,
        location=f"POINT({data.longitude} {data.latitude})",
        source=data.source,
        confidence=data.confidence,
        detected_at=data.detected_at,
        affected_hectares=data.affected_hectares,
        wind_direction=data.wind_direction,
        wind_speed=data.wind_speed,
        humidity=data.humidity,
        temperature=data.temperature,
    )
    db.add(incident)
    await db.flush()
    return IncidentRead.model_validate(incident)


async def update_incident(
    db: AsyncSession,
    incident_id: uuid.UUID,
    data: IncidentUpdate,
) -> IncidentRead:
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise NotFoundException("Incidente")

    if data.title is not None:
        incident.title = data.title
    if data.type is not None:
        incident.type = data.type
    if data.severity is not None:
        incident.severity = data.severity
    if data.protected_area_id is not None:
        incident.protected_area_id = data.protected_area_id
    if data.latitude is not None:
        incident.latitude = data.latitude
    if data.longitude is not None:
        incident.longitude = data.longitude
    if data.source is not None:
        incident.source = data.source
    if data.confidence is not None:
        incident.confidence = data.confidence
    if data.detected_at is not None:
        incident.detected_at = data.detected_at
    if data.affected_hectares is not None:
        incident.affected_hectares = data.affected_hectares
    if data.wind_direction is not None:
        incident.wind_direction = data.wind_direction
    if data.wind_speed is not None:
        incident.wind_speed = data.wind_speed
    if data.humidity is not None:
        incident.humidity = data.humidity
    if data.temperature is not None:
        incident.temperature = data.temperature

    incident.updated_at = datetime.now(UTC).replace(tzinfo=None)
    await db.flush()
    return IncidentRead.model_validate(incident)


async def update_incident_status(
    db: AsyncSession,
    incident_id: uuid.UUID,
    data: IncidentStatusUpdate,
    actor: object,
) -> IncidentRead:
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise NotFoundException("Incidente")

    incident.status = data.status
    incident.updated_at = datetime.now(UTC).replace(tzinfo=None)

    event = IncidentEvent(
        incident_id=incident.id,
        type="status_change",
        actor_id=actor.id,  # type: ignore[attr-defined]
        actor_name=actor.name,  # type: ignore[attr-defined]
        description=f"Status alterado para {data.status}: {data.reason}",
        timestamp=datetime.now(UTC).replace(tzinfo=None),
    )
    db.add(event)
    await db.flush()
    return IncidentRead.model_validate(incident)


async def get_incident_timeline(
    db: AsyncSession,
    incident_id: uuid.UUID,
) -> list[IncidentEventRead]:
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise NotFoundException("Incidente")

    events_result = await db.execute(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.timestamp)
    )
    events = events_result.scalars().all()
    return [IncidentEventRead.model_validate(e) for e in events]


async def add_incident_event(
    db: AsyncSession,
    incident_id: uuid.UUID,
    data: IncidentEventCreate,
    actor: object,
) -> IncidentEventRead:
    result = await db.execute(select(Incident).where(Incident.id == incident_id))
    incident = result.scalar_one_or_none()
    if not incident:
        raise NotFoundException("Incidente")

    ts = data.timestamp if data.timestamp is not None else datetime.now(UTC).replace(tzinfo=None)
    event = IncidentEvent(
        incident_id=incident_id,
        type=data.type,
        actor_id=actor.id,  # type: ignore[attr-defined]
        actor_name=actor.name,  # type: ignore[attr-defined]
        description=data.description,
        timestamp=ts,
    )
    db.add(event)
    await db.flush()
    return IncidentEventRead.model_validate(event)


_ACTIVE_STATUSES = [
    IncidentStatus.DETECTED,
    IncidentStatus.MONITORING,
    IncidentStatus.ACTIVE,
    IncidentStatus.PROTOCOL_ACTIVATED,
]

_SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


async def get_war_room(db: AsyncSession) -> WarRoomSummary:
    active_result = await db.execute(
        select(Incident)
        .where(Incident.status.in_(_ACTIVE_STATUSES))
        .order_by(Incident.created_at.desc())
    )
    active_incidents = active_result.scalars().all()

    # Sort by severity (critical first) then created_at desc
    active_incidents_sorted = sorted(
        active_incidents,
        key=lambda i: (_SEVERITY_ORDER.get(i.severity, 99), i.created_at),
    )

    incident_ids = [i.id for i in active_incidents_sorted]

    if incident_ids:
        events_result = await db.execute(
            select(IncidentEvent)
            .where(IncidentEvent.incident_id.in_(incident_ids))
            .order_by(IncidentEvent.timestamp.desc())
            .limit(10)
        )
        latest_events = events_result.scalars().all()
    else:
        latest_events = []

    by_severity: dict[str, int] = {}
    for incident in active_incidents_sorted:
        sev = incident.severity
        by_severity[sev] = by_severity.get(sev, 0) + 1

    return WarRoomSummary(
        active_incidents=[IncidentRead.model_validate(i) for i in active_incidents_sorted],
        total_active=len(active_incidents_sorted),
        by_severity=by_severity,
        latest_events=[IncidentEventRead.model_validate(e) for e in latest_events],
    )
