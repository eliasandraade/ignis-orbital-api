"""Create a real administrator out-of-band (inside the service, never via the API).

Needed because operational environments never run the demo seed: a fresh
staging/production database has no user at all, and the demo-account
revocation procedure must not leave the system without an administrator.

    python -m seed.bootstrap_admin --email admin@orgao.example --name "Nome Completo"

The password is read from stdin (prompted twice on a terminal) — never from
argv, environment variables or logs. The same policy as the admin API applies
(app/core/passwords.py). Refuses when the e-mail already exists. When a
legitimate active administrator already exists it refuses unless --additional
is passed. Every creation is written to the audit log.
"""

import argparse
import asyncio
import getpass
import sys

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.users.schemas import UserCreate


def read_password(stream=sys.stdin) -> str:
    if stream.isatty():
        first = getpass.getpass("Senha do administrador: ")
        if first != getpass.getpass("Confirme a senha: "):
            raise SystemExit("As senhas não conferem.")
        return first
    # Strip only the line terminator (\n or \r\n from Windows pipes); a stray
    # "\r" would create an admin whose password nobody can type.
    return stream.readline().rstrip("\r\n")


async def legitimate_admins(db: AsyncSession) -> int:
    """Active admins that are neither demo accounts nor using published passwords."""
    from app.users.model import User
    from seed.demo_users import scan

    total = await db.scalar(
        select(func.count()).select_from(User).where(User.role == "admin", User.is_active)
    )
    risky_admins = sum(
        1 for f in await scan(db) if f.risky and f.is_active and f.role == "admin"
    )
    return int(total or 0) - risky_admins


async def create_admin(db: AsyncSession, data: UserCreate, additional: bool) -> str:
    from app.core.audit import log_action
    from app.users.model import User

    if await db.scalar(select(User).where(func.lower(User.email) == data.email.lower())):
        raise SystemExit(f"Recusado: já existe usuário com o e-mail {data.email}.")
    if not additional and await legitimate_admins(db) > 0:
        raise SystemExit(
            "Recusado: já existe administrador ativo legítimo. "
            "Use o painel/API, ou --additional se for intencional."
        )
    user = User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password),
        role="admin",
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await log_action(
        db,
        "user.bootstrap_admin_created",
        "User",
        str(user.id),
        actor_name="ops:seed.bootstrap_admin",
    )
    await db.commit()
    return str(user.id)


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m seed.bootstrap_admin")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--additional", action="store_true")
    args = parser.parse_args(argv)

    try:
        data = UserCreate(
            name=args.name, email=args.email, password=read_password(), role="admin"
        )
    except ValidationError as exc:
        print("Recusado:", "; ".join(e["msg"] for e in exc.errors()))
        return 1

    import app.main  # noqa: F401 — registers every ORM mapper
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        user_id = await create_admin(db, data, args.additional)
    print(f"Administrador criado: {data.email} (id {user_id}).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
