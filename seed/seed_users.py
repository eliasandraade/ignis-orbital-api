from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.users.model import User
from seed.base import get_or_none

USERS = [
    {
        "name": "Admin IGNIS",
        "email": "admin@ignis-orbital.com",
        "password": "admin@123",
        "role": "admin",
    },
    {
        "name": "Gestor SEMACE",
        "email": "gestor@semace.ce.gov.br",
        "password": "gestor@123",
        "role": "gestor",
    },
    {
        "name": "Operador Defesa Civil",
        "email": "operador@defesacivil.ce.gov.br",
        "password": "operador@123",
        "role": "orgao",
    },
    {
        "name": "Agente de Campo",
        "email": "campo@ibama.gov.br",
        "password": "campo@123",
        "role": "campo",
    },
]


async def seed_users(db: AsyncSession) -> None:
    print("  -> Seeding users...")
    for u in USERS:
        existing = await get_or_none(db, User, email=u["email"])
        if existing is None:
            user = User(
                name=u["name"],
                email=u["email"],
                password_hash=hash_password(u["password"]),
                role=u["role"],
            )
            db.add(user)
    await db.flush()
    print(f"  -> Users OK ({len(USERS)} entries checked)")
