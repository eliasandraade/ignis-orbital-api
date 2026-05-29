import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_action
from app.core.enums import ReportStatus, ReportType, ReportUrgency, UserRole
from app.core.pagination import Page
from app.database import get_db
from app.dependencies import require_role
from app.reports import service as report_service
from app.reports.schemas import ReportCreate, ReportRead, ReportStatusUpdate

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.post("", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
async def submit_report(
    body: ReportCreate,
    db: AsyncSession = Depends(get_db),
):
    report = await report_service.create_report(db, body)
    await log_action(
        db,
        "report.submitted",
        "PublicReport",
        str(report.id),
        actor_name=body.reporter_name or "anônimo",
    )
    await db.commit()
    return report


@router.get("", response_model=Page[ReportRead])
async def list_reports(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: ReportStatus | None = Query(None),
    urgency: ReportUrgency | None = Query(None),
    type: ReportType | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
):
    return await report_service.list_reports(db, page, size, status, urgency, type)


# IMPORTANT: /lookup must be registered BEFORE /{report_id} to avoid FastAPI
# trying to parse "lookup" as a UUID and returning 422.
@router.get("/lookup", response_model=ReportRead)
async def lookup_by_protocol(
    protocol: str = Query(..., description="Protocolo no formato RP-YYYYMMDD-XXXX"),
    db: AsyncSession = Depends(get_db),
):
    return await report_service.get_report_by_protocol(db, protocol)


@router.get("/{report_id}", response_model=ReportRead)
async def get_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
):
    return await report_service.get_report(db, report_id)


@router.patch("/{report_id}/status", response_model=ReportRead)
async def update_report_status(
    report_id: uuid.UUID,
    body: ReportStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
):
    report = await report_service.update_report_status(db, report_id, body)
    await log_action(
        db,
        "report.status_updated",
        "PublicReport",
        str(report_id),
        actor_name=current_user.name,
        actor_id=current_user.id,
        metadata={"new_status": body.status},
    )
    await db.commit()
    return report
