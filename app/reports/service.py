import random
import string
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import IncidentSource, IncidentStatus, ReportStatus, ReportUrgency
from app.core.exceptions import ConflictException, NotFoundException
from app.core.pagination import Page
from app.reports.model import PublicReport
from app.reports.schemas import ReportCreate, ReportRead, ReportStatusUpdate


def _generate_protocol() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"RP-{date.today().strftime('%Y%m%d')}-{suffix}"


async def create_report(db: AsyncSession, data: ReportCreate) -> ReportRead:
    protocol = _generate_protocol()
    location_wkt = (
        f"POINT({data.longitude} {data.latitude})"
        if data.latitude is not None and data.longitude is not None
        else None
    )
    report = PublicReport(
        protocol=protocol,
        type=data.type,
        description=data.description,
        urgency=data.urgency,
        status=ReportStatus.PENDING,
        reporter_name=data.reporter_name,
        contact=data.contact,
        is_anonymous=data.is_anonymous,
        latitude=data.latitude,
        longitude=data.longitude,
        location=location_wkt,
        protected_area_id=data.protected_area_id,
        evidence_urls=data.evidence_urls or [],
    )
    db.add(report)
    await db.flush()
    return ReportRead.model_validate(report)


async def list_reports(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    status: ReportStatus | None = None,
    urgency: ReportUrgency | None = None,
    report_type: str | None = None,
) -> Page[ReportRead]:
    offset = (page - 1) * size
    query = select(PublicReport)
    count_query = select(func.count()).select_from(PublicReport)

    if status:
        query = query.where(PublicReport.status == status)
        count_query = count_query.where(PublicReport.status == status)
    if urgency:
        query = query.where(PublicReport.urgency == urgency)
        count_query = count_query.where(PublicReport.urgency == urgency)
    if report_type:
        query = query.where(PublicReport.type == report_type)
        count_query = count_query.where(PublicReport.type == report_type)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    result = await db.execute(
        query.order_by(PublicReport.created_at.desc()).offset(offset).limit(size)
    )
    reports = result.scalars().all()
    return Page.create(
        items=[ReportRead.model_validate(r) for r in reports],
        total=total,
        page=page,
        size=size,
    )


async def get_report(db: AsyncSession, report_id: uuid.UUID) -> ReportRead:
    result = await db.execute(select(PublicReport).where(PublicReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise NotFoundException("Reporte")
    return ReportRead.model_validate(report)


async def get_report_by_protocol(db: AsyncSession, protocol: str) -> ReportRead:
    result = await db.execute(select(PublicReport).where(PublicReport.protocol == protocol))
    report = result.scalar_one_or_none()
    if not report:
        raise NotFoundException("Reporte")
    return ReportRead.model_validate(report)


async def convert_to_incident(
    db: AsyncSession,
    report_id: uuid.UUID,
    actor: object,
) -> object:
    """Convert a validated/pending public report into an incident. Returns IncidentRead."""
    from app.incidents.model import Incident
    from app.incidents.schemas import IncidentRead as IncidentReadSchema
    from app.incidents.service import _generate_code

    result = await db.execute(select(PublicReport).where(PublicReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise NotFoundException("Reporte")
    if report.status not in (ReportStatus.PENDING, ReportStatus.VALIDATED):
        raise ConflictException(
            f"Reporte com status '{report.status}' não pode ser convertido em incidente"
        )
    if report.linked_incident_id is not None:
        raise ConflictException("Reporte já foi convertido em incidente")

    location_wkt = (
        f"POINT({report.longitude} {report.latitude})"
        if report.latitude is not None and report.longitude is not None
        else None
    )
    incident = Incident(
        code=_generate_code(),
        title=f"Incidente originado de denúncia {report.protocol}",
        type=report.type,
        severity="medium",
        status=IncidentStatus.DETECTED,
        protected_area_id=report.protected_area_id,
        latitude=report.latitude,
        longitude=report.longitude,
        location=location_wkt,
        source=IncidentSource.REPORT,
        confidence=0.7,
        detected_at=report.created_at,
    )
    db.add(incident)
    await db.flush()

    report.linked_incident_id = incident.id
    report.status = ReportStatus.CONVERTED
    report.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()

    return IncidentReadSchema.model_validate(incident)


async def update_report_status(
    db: AsyncSession,
    report_id: uuid.UUID,
    data: ReportStatusUpdate,
) -> ReportRead:
    result = await db.execute(select(PublicReport).where(PublicReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise NotFoundException("Reporte")

    report.status = data.status
    if data.validation_notes is not None:
        report.validation_notes = data.validation_notes
    report.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()
    return ReportRead.model_validate(report)
