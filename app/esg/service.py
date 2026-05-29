import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.core.pagination import Page
from app.esg.model import ESGReport
from app.esg.schemas import ESGReportCreate, ESGReportRead


async def list_reports(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    area_id: uuid.UUID | None = None,
) -> Page[ESGReportRead]:
    offset = (page - 1) * size
    query = select(ESGReport)
    count_query = select(func.count()).select_from(ESGReport)

    if area_id is not None:
        query = query.where(ESGReport.protected_area_id == area_id)
        count_query = count_query.where(ESGReport.protected_area_id == area_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    result = await db.execute(
        query.order_by(ESGReport.period_start.desc()).offset(offset).limit(size)
    )
    reports = result.scalars().all()
    return Page.create(
        items=[ESGReportRead.model_validate(r) for r in reports],
        total=total,
        page=page,
        size=size,
    )


async def get_report(db: AsyncSession, report_id: uuid.UUID) -> ESGReportRead:
    result = await db.execute(select(ESGReport).where(ESGReport.id == report_id))
    report = result.scalar_one_or_none()
    if report is None:
        raise NotFoundException("Relatório ESG")
    return ESGReportRead.model_validate(report)


async def create_report(db: AsyncSession, data: ESGReportCreate) -> ESGReportRead:
    report = ESGReport(
        protected_area_id=data.protected_area_id,
        period_start=data.period_start,
        period_end=data.period_end,
        monitored_area_ha=data.monitored_area_ha,
        incidents_resolved=data.incidents_resolved,
        average_response_minutes=data.average_response_minutes,
        heat_spots_detected=data.heat_spots_detected,
        vegetation_loss_estimated_ha=data.vegetation_loss_estimated_ha,
        prevented_impact_estimate=data.prevented_impact_estimate,
        ods=data.ods,
    )
    db.add(report)
    await db.flush()
    return ESGReportRead.model_validate(report)
