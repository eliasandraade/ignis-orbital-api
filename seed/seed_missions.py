from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.incidents.model import Incident
from app.missions.model import Mission
from app.teams.model import FieldTeam
from seed.base import get_or_none

MISSIONS = [
    {
        "incident_code": "IGN-CE-2026-0041",
        "team_name": "Brigada Alfa",
        "status": "active",
        "objective": "Contenção e combate ao incêndio na zona norte da RPPN",
        "notes": "Prioridade máxima — 87ha comprometidos",
    },
    {
        "incident_code": "IGN-CE-2026-0041",
        "team_name": "Equipe de Monitoramento Norte",
        "status": "active",
        "objective": "Mapeamento aéreo com drone e monitoramento meteorológico",
        "notes": "Coordenar com Brigada Alfa para rota segura",
    },
    {
        "incident_code": "IGN-CE-2026-0040",
        "team_name": "Brigada Beta",
        "status": "planned",
        "objective": "Inspeção e documentação do desmatamento",
        "notes": "Aguardando confirmação de acesso ao local",
    },
]


async def seed_missions(db: AsyncSession) -> None:
    print("  -> Seeding missions...")
    now = datetime.now(UTC)

    added = 0
    for m in MISSIONS:
        incident = await get_or_none(db, Incident, code=m["incident_code"])
        team = await get_or_none(db, FieldTeam, name=m["team_name"])

        if incident is None:
            print(f"  -> WARNING: incident '{m['incident_code']}' not found, skipping mission")
            continue
        if team is None:
            print(f"  -> WARNING: team '{m['team_name']}' not found, skipping mission")
            continue

        # Deduplication: skip if a mission for the same incident, team and objective already exists
        result = await db.execute(
            select(Mission).where(
                Mission.incident_id == incident.id,
                Mission.team_id == team.id,
                Mission.objective == m["objective"],
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            continue

        started_at = None
        if m["status"] == "active":
            started_at = now - timedelta(hours=2)

        mission = Mission(
            incident_id=incident.id,
            team_id=team.id,
            status=m["status"],
            objective=m["objective"],
            notes=m["notes"],
            started_at=started_at,
        )
        db.add(mission)
        added += 1

    await db.flush()
    print(f"  -> Missions OK ({added} entries added, {len(MISSIONS) - added} skipped)")
