import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.schemas import AuditLogRead
from app.audit.service import list_logs
from app.core.enums import UserRole
from app.core.pagination import Page
from app.database import get_db
from app.dependencies import require_role

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/audit-logs", response_model=Page[AuditLogRead])
async def get_audit_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    action: str | None = Query(None),
    entity_type: str | None = Query(None),
    user_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.ADMIN)),
) -> Page[AuditLogRead]:
    return await list_logs(
        db=db,
        page=page,
        size=size,
        action=action,
        entity_type=entity_type,
        user_id=user_id,
    )
