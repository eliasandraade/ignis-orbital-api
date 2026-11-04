import csv
import io
import json
import uuid
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.model import AuditLog
from app.audit.schemas import AuditLogRead
from app.core.pagination import Page

# Metadata keys never shown or exported, whatever a writer put there.
_SECRET_MARKERS = ("password", "senha", "token", "secret", "hash", "key", "authorization")
EXPORT_LIMIT = 10_000


def sanitize(value):
    """Recursively replace values under secret-looking keys."""
    if isinstance(value, dict):
        return {
            k: "[omitido]" if any(m in str(k).lower() for m in _SECRET_MARKERS) else sanitize(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return value


def _conditions(
    *,
    action: str | None,
    entity_type: str | None,
    entity_id: str | None,
    user_id: uuid.UUID | None,
    involving_user: uuid.UUID | None,
    actor: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list:
    conditions = []
    if action:
        conditions.append(AuditLog.action.ilike(f"%{action}%"))
    if entity_type:
        conditions.append(AuditLog.entity_type == entity_type)
    if entity_id:
        conditions.append(AuditLog.entity_id == entity_id)
    if user_id is not None:
        conditions.append(AuditLog.user_id == user_id)
    if involving_user is not None:
        conditions.append(
            or_(
                AuditLog.user_id == involving_user,
                and_(AuditLog.entity_type == "User", AuditLog.entity_id == str(involving_user)),
            )
        )
    if actor:
        conditions.append(func.lower(AuditLog.actor_name).like(f"%{actor.lower()}%"))
    # created_at is stored as naive UTC by log_action.
    if date_from is not None:
        conditions.append(AuditLog.created_at >= _naive_utc(date_from))
    if date_to is not None:
        conditions.append(AuditLog.created_at < _naive_utc(date_to))
    return conditions


def _naive_utc(value: datetime) -> datetime:
    from datetime import UTC

    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def _read(log: AuditLog) -> AuditLogRead:
    item = AuditLogRead.model_validate(log)
    item.metadata_json = sanitize(item.metadata_json)
    return item


async def list_logs(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    action: str | None = None,
    entity_type: str | None = None,
    user_id: uuid.UUID | None = None,
    *,
    entity_id: str | None = None,
    involving_user: uuid.UUID | None = None,
    actor: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> Page[AuditLogRead]:
    conditions = _conditions(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        user_id=user_id,
        involving_user=involving_user,
        actor=actor,
        date_from=date_from,
        date_to=date_to,
    )
    total = await db.scalar(select(func.count()).select_from(AuditLog).where(*conditions))
    logs = (
        await db.scalars(
            select(AuditLog)
            .where(*conditions)
            .order_by(AuditLog.created_at.desc(), AuditLog.id)
            .offset((page - 1) * size)
            .limit(size)
        )
    ).all()
    return Page.create(items=[_read(log) for log in logs], total=total or 0, page=page, size=size)


async def export_csv(db: AsyncSession, **filters) -> tuple[str, int]:
    """CSV of the filtered events (newest first, at most EXPORT_LIMIT rows).
    Metadata is sanitized like the API response; returns (csv, rows)."""
    conditions = _conditions(**filters)
    logs = (
        await db.scalars(
            select(AuditLog)
            .where(*conditions)
            .order_by(AuditLog.created_at.desc(), AuditLog.id)
            .limit(EXPORT_LIMIT)
        )
    ).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "created_at_utc",
            "action",
            "actor_name",
            "actor_id",
            "entity_type",
            "entity_id",
            "metadata",
        ]
    )
    for log in logs:
        writer.writerow(
            [
                log.created_at.isoformat(),
                _csv_safe(log.action),
                _csv_safe(log.actor_name),
                str(log.user_id or ""),
                _csv_safe(log.entity_type),
                _csv_safe(log.entity_id),
                _csv_safe(json.dumps(sanitize(log.metadata_json or {}), ensure_ascii=False)),
            ]
        )
    return buffer.getvalue(), len(logs)


def _csv_safe(value: str) -> str:
    # A cell starting with = + - @ would run as a formula in a spreadsheet.
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value
