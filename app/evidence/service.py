import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.core.pagination import Page
from app.evidence.model import Evidence
from app.evidence.schemas import EvidenceCreate, EvidenceRead


async def list_evidence(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    incident_id: uuid.UUID | None = None,
    report_id: uuid.UUID | None = None,
) -> Page[EvidenceRead]:
    offset = (page - 1) * size
    query = select(Evidence)
    count_query = select(func.count()).select_from(Evidence)

    if incident_id is not None:
        query = query.where(Evidence.incident_id == incident_id)
        count_query = count_query.where(Evidence.incident_id == incident_id)
    if report_id is not None:
        query = query.where(Evidence.report_id == report_id)
        count_query = count_query.where(Evidence.report_id == report_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    result = await db.execute(
        query.order_by(Evidence.created_at.desc()).offset(offset).limit(size)
    )
    items = result.scalars().all()
    return Page.create(
        items=[EvidenceRead.model_validate(e) for e in items],
        total=total,
        page=page,
        size=size,
    )


async def get_evidence_item(db: AsyncSession, evidence_id: uuid.UUID) -> EvidenceRead:
    result = await db.execute(select(Evidence).where(Evidence.id == evidence_id))
    evidence = result.scalar_one_or_none()
    if not evidence:
        raise NotFoundException("Evidência")
    return EvidenceRead.model_validate(evidence)


async def create_evidence(
    db: AsyncSession,
    data: EvidenceCreate,
    actor: object,
) -> EvidenceRead:
    location = None
    if data.latitude is not None and data.longitude is not None:
        location = f"POINT({data.longitude} {data.latitude})"

    evidence = Evidence(
        incident_id=data.incident_id,
        report_id=data.report_id,
        type=data.type,
        url=data.url,
        description=data.description,
        latitude=data.latitude,
        longitude=data.longitude,
        location=location,
        source=data.source,
    )
    db.add(evidence)
    await db.flush()
    return EvidenceRead.model_validate(evidence)
