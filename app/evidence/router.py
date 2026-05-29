import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_action
from app.core.enums import UserRole
from app.core.pagination import Page
from app.database import get_db
from app.dependencies import require_role
from app.evidence import service as evidence_service
from app.evidence.schemas import EvidenceCreate, EvidenceRead

router = APIRouter(prefix="/api/v1/evidence", tags=["evidence"])


@router.get("", response_model=Page[EvidenceRead])
async def list_evidence(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    incident_id: uuid.UUID | None = Query(None),
    report_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.CAMPO)),
) -> Page[EvidenceRead]:
    return await evidence_service.list_evidence(db, page, size, incident_id, report_id)


@router.get("/{evidence_id}", response_model=EvidenceRead)
async def get_evidence_item(
    evidence_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.CAMPO)),
) -> EvidenceRead:
    return await evidence_service.get_evidence_item(db, evidence_id)


@router.post("", response_model=EvidenceRead, status_code=status.HTTP_201_CREATED)
async def create_evidence(
    body: EvidenceCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.CAMPO)),
) -> EvidenceRead:
    evidence = await evidence_service.create_evidence(db, body, current_user)
    await log_action(
        db,
        "evidence.submitted",
        "Evidence",
        str(evidence.id),
        actor_name=current_user.name,
        actor_id=current_user.id,
    )
    await db.commit()
    return evidence
