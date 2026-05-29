import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_action
from app.core.enums import UserRole
from app.core.pagination import Page
from app.database import get_db
from app.dependencies import require_role
from app.esg import service as esg_service
from app.esg.schemas import ESGReportCreate, ESGReportRead

router = APIRouter(prefix="/api/v1/esg", tags=["esg"])


@router.get("", response_model=Page[ESGReportRead])
async def list_esg_reports(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    area_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(require_role(UserRole.ORGAO)),
) -> Page[ESGReportRead]:
    return await esg_service.list_reports(db, page, size, area_id)


@router.get("/{report_id}", response_model=ESGReportRead)
async def get_esg_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(require_role(UserRole.ORGAO)),
) -> ESGReportRead:
    return await esg_service.get_report(db, report_id)


@router.post("", response_model=ESGReportRead, status_code=status.HTTP_201_CREATED)
async def create_esg_report(
    body: ESGReportCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.ORGAO)),
) -> ESGReportRead:
    report = await esg_service.create_report(db, body)
    await log_action(
        db,
        "esg.report_created",
        "ESGReport",
        str(report.id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return report
