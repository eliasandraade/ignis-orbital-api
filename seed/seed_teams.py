from sqlalchemy.ext.asyncio import AsyncSession

from app.teams.model import FieldTeam
from app.users.model import User
from seed.base import get_or_none

TEAMS = [
    {
        "name": "Brigada Alfa",
        "type": "firefighting",
        "status": "mobilized",
        "notes": "Atuando na RPPN Elias Andrade",
    },
    {
        "name": "Brigada Beta",
        "type": "firefighting",
        "status": "mobilized",
        "notes": "Suporte ao Parque do Cocó",
    },
    {
        "name": "Equipe de Monitoramento Norte",
        "type": "monitoring",
        "status": "mobilized",
        "notes": "Cobertura da APA Baturité",
    },
    {
        "name": "Equipe de Resgate Litoral",
        "type": "rescue",
        "status": "standby",
        "notes": "Base em Fortaleza",
    },
    {
        "name": "Equipe de Patrulha Sul",
        "type": "patrol",
        "status": "available",
        "notes": "Rotina diária",
    },
    {
        "name": "Suporte Logístico",
        "type": "support",
        "status": "returning",
        "notes": "Retornando de missão",
    },
]


async def seed_teams(db: AsyncSession) -> None:
    print("  -> Seeding teams...")
    for t in TEAMS:
        existing = await get_or_none(db, FieldTeam, name=t["name"])
        if existing is None:
            team = FieldTeam(
                name=t["name"],
                type=t["type"],
                status=t["status"],
                notes=t["notes"],
            )
            db.add(team)
    await db.flush()

    # Vincula Agente de Campo à Brigada Alfa
    brigada_alfa = await get_or_none(db, FieldTeam, name="Brigada Alfa")
    campo_user = await get_or_none(db, User, email="campo@ibama.gov.br")
    if brigada_alfa and campo_user and campo_user.team_id is None:
        campo_user.team_id = brigada_alfa.id
        db.add(campo_user)
        await db.flush()

    print(f"  -> Teams OK ({len(TEAMS)} entries checked)")
