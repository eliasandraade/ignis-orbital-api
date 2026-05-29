from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.database import get_db
from app.dependencies import require_role

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role(UserRole.ORGAO)),
) -> dict:
    from app.evidence.model import Evidence  # noqa: F401 — imported for completeness
    from app.incidents.model import Incident
    from app.missions.model import Mission
    from app.protected_areas.model import ProtectedArea
    from app.reports.model import PublicReport
    from app.teams.model import FieldTeam
    from app.users.model import User

    results = await db.execute(select(func.count()).select_from(Incident))
    total_incidents = results.scalar_one()

    results = await db.execute(select(func.count()).select_from(PublicReport))
    total_reports = results.scalar_one()

    results = await db.execute(select(func.count()).select_from(ProtectedArea))
    total_areas = results.scalar_one()

    results = await db.execute(
        select(func.count()).select_from(User).where(User.is_active == True)  # noqa: E712
    )
    total_users = results.scalar_one()

    results = await db.execute(select(func.count()).select_from(FieldTeam))
    total_teams = results.scalar_one()

    results = await db.execute(select(func.count()).select_from(Mission))
    total_missions = results.scalar_one()

    return {
        "total_incidents": total_incidents,
        "total_reports": total_reports,
        "total_protected_areas": total_areas,
        "total_active_users": total_users,
        "total_teams": total_teams,
        "total_missions": total_missions,
    }
