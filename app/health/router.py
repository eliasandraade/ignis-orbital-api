import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(tags=["saúde do serviço"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health() -> dict:
    """Liveness. Public, so it reveals nothing about the deployment: version and
    environment are in the admin cockpit (/api/v1/admin/settings)."""
    return {"status": "ok", "service": "ignis-orbital-api"}


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as exc:
        # Never echo the driver error: it may contain host, user or DSN details.
        logger.warning("readiness check failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail={"status": "unavailable", "database": "unreachable"},
        ) from exc
