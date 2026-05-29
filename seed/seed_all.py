import asyncio

from app.database import AsyncSessionLocal


async def run_all() -> None:
    print("==> Iniciando seed demonstrativo IGNIS Orbital...")
    async with AsyncSessionLocal() as db:
        from seed.seed_areas import seed_areas
        from seed.seed_esg import seed_esg
        from seed.seed_incidents import seed_incidents
        from seed.seed_missions import seed_missions
        from seed.seed_reports import seed_reports
        from seed.seed_resources import seed_resources
        from seed.seed_teams import seed_teams
        from seed.seed_users import seed_users

        await seed_users(db)
        await seed_teams(db)
        await seed_areas(db)
        await seed_incidents(db)
        await seed_reports(db)
        await seed_resources(db)
        await seed_missions(db)
        await seed_esg(db)
        await db.commit()
    print("==> Seed concluído com sucesso!")


if __name__ == "__main__":
    asyncio.run(run_all())
