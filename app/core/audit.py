from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def log_action(
    db: AsyncSession,
    action: str,
    entity_type: str,
    entity_id: str | UUID | int,
    actor_name: str = "sistema",
    actor_id: UUID | None = None,
    metadata: dict | None = None,
) -> None:
    from app.audit.model import AuditLog  # lazy import para evitar circular

    log = AuditLog(
        user_id=actor_id,
        actor_name=actor_name,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        metadata_json=metadata or {},
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(log)
    # sem commit aqui — operação principal faz o commit
