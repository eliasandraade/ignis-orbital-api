import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.model import AuditLog
from app.audit.schemas import AuditLogRead
from app.core.pagination import Page


async def list_logs(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    action: str | None = None,
    entity_type: str | None = None,
    user_id: uuid.UUID | None = None,
) -> Page[AuditLogRead]:
    offset = (page - 1) * size
    query = select(AuditLog)
    count_query = select(func.count()).select_from(AuditLog)

    if action is not None:
        query = query.where(AuditLog.action.ilike(f"%{action}%"))
        count_query = count_query.where(AuditLog.action.ilike(f"%{action}%"))
    if entity_type is not None:
        query = query.where(AuditLog.entity_type == entity_type)
        count_query = count_query.where(AuditLog.entity_type == entity_type)
    if user_id is not None:
        query = query.where(AuditLog.user_id == user_id)
        count_query = count_query.where(AuditLog.user_id == user_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    result = await db.execute(
        query.order_by(AuditLog.created_at.desc()).offset(offset).limit(size)
    )
    logs = result.scalars().all()
    return Page.create(
        items=[AuditLogRead.model_validate(log) for log in logs],
        total=total,
        page=page,
        size=size,
    )
