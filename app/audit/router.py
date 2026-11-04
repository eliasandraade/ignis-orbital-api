import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.schemas import AuditLogRead
from app.audit.service import EXPORT_LIMIT, export_csv, list_logs
from app.core.audit import log_action
from app.core.enums import UserRole
from app.core.pagination import Page
from app.core.rate_limit import rate_limit
from app.database import get_db
from app.dependencies import require_role

router = APIRouter(prefix="/api/v1/admin", tags=["administração: auditoria"])


def _filters(
    action: str | None = Query(None, max_length=100, description="Trecho do nome da ação"),
    entity_type: str | None = Query(None, max_length=100),
    entity_id: str | None = Query(None, max_length=100),
    user_id: uuid.UUID | None = Query(None, description="Ator (usuário que executou)"),
    involving_user: uuid.UUID | None = Query(None, description="Ator ou alvo"),
    actor: str | None = Query(None, max_length=100, description="Trecho do nome do ator"),
    date_from: datetime | None = Query(None, alias="from", description="Início (ISO 8601)"),
    date_to: datetime | None = Query(None, alias="to", description="Fim exclusivo (ISO 8601)"),
) -> dict:
    return {
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "user_id": user_id,
        "involving_user": involving_user,
        "actor": actor,
        "date_from": date_from,
        "date_to": date_to,
    }


@router.get(
    "/audit-logs",
    response_model=Page[AuditLogRead],
    responses={
        401: {"description": "Sem autenticação"},
        403: {"description": "Somente administrador"},
    },
)
async def get_audit_logs(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    filters: dict = Depends(_filters),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.ADMIN)),
) -> Page[AuditLogRead]:
    """Trilha de auditoria (ações de usuários no sistema), mais recentes primeiro.
    Chaves de metadados com aparência de segredo são omitidas."""
    return await list_logs(db=db, page=page, size=size, **filters)


@router.get(
    "/audit-logs/export",
    responses={
        200: {"content": {"text/csv": {}}, "description": f"CSV (até {EXPORT_LIMIT} linhas)"},
        401: {"description": "Sem autenticação"},
        403: {"description": "Somente administrador"},
    },
    dependencies=[Depends(rate_limit("audit-export", limit=10))],
)
async def export_audit_logs(
    filters: dict = Depends(_filters),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.ADMIN)),
) -> Response:
    """Exporta os eventos filtrados. A própria exportação fica registrada na auditoria."""
    body, rows = await export_csv(db, **filters)
    await log_action(
        db,
        "audit.exported",
        "AuditLog",
        "export",
        actor_name=current_user.name,
        actor_id=current_user.id,
        metadata={
            "result": "success",
            "rows": rows,
            "filters": {k: str(v) for k, v in filters.items() if v is not None},
        },
    )
    await db.commit()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%MZ")
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="ignis-auditoria-{stamp}.csv"'},
    )
