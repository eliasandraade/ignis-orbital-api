import random
import string
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ReportStatus, ReportUrgency
from app.core.exceptions import NotFoundException
from app.core.pagination import Page
from app.reports.model import PublicReport
from app.reports.schemas import ReportCreate, ReportRead, ReportStatusUpdate


def _generate_protocol() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"RP-{date.today().strftime('%Y%m%d')}-{suffix}"


async def create_report(db: AsyncSession, data: ReportCreate) -> ReportRead:
    protocol = _generate_protocol()
    location_wkt = f"POINT({data.longitude} {data.latitude})"
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
    report.updated_at = datetime.now(UTC)
    await db.flush()
    return ReportRead.model_validate(report)
