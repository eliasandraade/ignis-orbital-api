import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.audit import log_action
from app.core.enums import ReportStatus, ReportType, ReportUrgency, UserRole
from app.core.pagination import Page
from app.core.rate_limit import rate_limit
from app.database import get_db
from app.dependencies import require_role
from app.reports import service as report_service
from app.reports.schemas import ReportCreate, ReportRead, ReportStatusPublic, ReportStatusUpdate

router = APIRouter(prefix="/api/v1/reports", tags=["denúncias"])

INTAKE_CLOSED_MESSAGE = (
    "O recebimento de denúncias está desativado nesta instalação. Em caso de incêndio, "
    "acione o Corpo de Bombeiros (193) ou a Defesa Civil (199)."
)


def _require_intake_open() -> None:
    if not get_settings().public_reports_accepting:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=INTAKE_CLOSED_MESSAGE)


@router.get("/intake")
async def report_intake() -> dict:
    """Informa se esta instalação recebe denúncias públicas (sem dados pessoais)."""
    accepting = get_settings().public_reports_accepting
    return {"accepting": accepting, "message": None if accepting else INTAKE_CLOSED_MESSAGE}


@router.post(
    "",
    response_model=ReportRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_require_intake_open), Depends(rate_limit("report-submit", limit=10))],
    responses={503: {"description": "Recebimento de denúncias desativado nesta instalação"}},
)
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


# IMPORTANT: static routes (/lookup, /validate etc.) must be before /{report_id}
@router.get(
    "/lookup",
    response_model=ReportStatusPublic,
    summary="Consulta pública de denúncia por protocolo",
    dependencies=[Depends(rate_limit("report-lookup", limit=30))],
    description="Retorna o status da denúncia sem expor dados pessoais do denunciante.",
)
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


@router.patch("/{report_id}/validate", response_model=ReportRead)
async def validate_report(
    report_id: uuid.UUID,
    validation_notes: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
):
    body = ReportStatusUpdate(status=ReportStatus.VALIDATED, validation_notes=validation_notes)
    report = await report_service.update_report_status(db, report_id, body)
    await log_action(
        db,
        "report.validated",
        "PublicReport",
        str(report_id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return report


@router.patch("/{report_id}/discard", response_model=ReportRead)
async def discard_report(
    report_id: uuid.UUID,
    validation_notes: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
):
    body = ReportStatusUpdate(status=ReportStatus.DISCARDED, validation_notes=validation_notes)
    report = await report_service.update_report_status(db, report_id, body)
    await log_action(
        db,
        "report.discarded",
        "PublicReport",
        str(report_id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return report


@router.post("/{report_id}/convert-to-incident", status_code=status.HTTP_201_CREATED)
async def convert_report_to_incident(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.GESTOR)),
):
    incident = await report_service.convert_to_incident(db, report_id, current_user)
    await log_action(
        db,
        "report.converted_to_incident",
        "PublicReport",
        str(report_id),
        actor_name=current_user.name,
        actor_id=current_user.id,
        metadata={"incident_code": incident.code},
    )
    await db.commit()
    return incident
