import asyncio

from app.config import DEMO_SEED_ENVS, get_settings
from app.database import AsyncSessionLocal


class DemoSeedRefusedError(RuntimeError):
    """Raised when the demo seed would run outside a demo/development environment."""


def ensure_seed_allowed() -> None:
    """The demo seed creates users with published passwords (see seed_users.py).

    It only runs with APP_ENV in development/test/demo. There is deliberately no
    override for staging or production: demonstrations use a separate
    APP_ENV=demo deployment with its own database.
    """
    settings = get_settings()
    if not settings.demo_seed_allowed:
        allowed = ", ".join(sorted(DEMO_SEED_ENVS))
        raise DemoSeedRefusedError(
            f"Seed demonstrativo recusado em APP_ENV={settings.app_env}. "
            f"Permitido apenas em: {allowed}."
        )


async def run_all() -> None:
    ensure_seed_allowed()
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
