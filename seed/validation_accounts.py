"""Local human-validation accounts (admin, gestor, campo). Never for a real deploy.

    IGNIS_VALIDATION_PASSWORD_ADMIN=... IGNIS_VALIDATION_PASSWORD_GESTOR=... \\
    IGNIS_VALIDATION_PASSWORD_CAMPO=... python -m seed.validation_accounts

Used by deploy/local/validate.sh, which generates random passwords per
installation and keeps them in a git-ignored file. Refuses to run unless
APP_ENV is development or test and no Railway variable is present, so it
cannot create known accounts in staging or production by mistake.
Idempotent: an existing account gets the given password and role again.
Every change is written to the audit log.
"""

import asyncio
import os
import sys

from sqlalchemy import func, select

ACCOUNTS = (
    ("admin", "admin.validacao@example.org", "Administrador (validação local)"),
    ("gestor", "gestor.validacao@example.org", "Gestor (validação local)"),
    ("campo", "campo.validacao@example.org", "Equipe de campo (validação local)"),
)
ALLOWED_ENVS = ("development", "test")


class RefusedError(Exception):
    """Not a local validation stack: nothing is created."""


def ensure_local_environment(environ=os.environ) -> None:
    app_env = environ.get("APP_ENV", "")
    if app_env not in ALLOWED_ENVS:
        raise RefusedError(f"Recusado: APP_ENV={app_env!r} (só development ou test).")
    railway = sorted(k for k in environ if k.startswith("RAILWAY_"))
    if railway:
        raise RefusedError(f"Recusado: variáveis do Railway presentes ({railway[0]}...).")


async def upsert_accounts(db, passwords: dict[str, str]) -> list[str]:
    from app.core.audit import log_action
    from app.core.security import hash_password
    from app.users.model import User
    from app.users.schemas import UserCreate

    done = []
    for role, email, name in ACCOUNTS:
        password = passwords.get(role)
        if not password:
            continue
        data = UserCreate(name=name, email=email, password=password, role=role)
        user = await db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            user = User(name=name, email=email, role=role, is_active=True, password_hash="")
            db.add(user)
        user.password_hash = hash_password(data.password)
        user.role, user.is_active = role, True
        await db.flush()
        await log_action(
            db,
            "user.local_validation_account",
            "User",
            str(user.id),
            actor_name="ops:seed.validation_accounts",
            metadata={"email": email, "role": role},
        )
        done.append(email)
    await db.commit()
    return done


async def _main() -> int:
    ensure_local_environment()
    passwords = {
        role: os.environ.get(f"IGNIS_VALIDATION_PASSWORD_{role.upper()}", "")
        for role, _, _ in ACCOUNTS
    }
    if not any(passwords.values()):
        raise RefusedError("Nenhuma senha informada (IGNIS_VALIDATION_PASSWORD_<PAPEL>).")
    import app.main  # noqa: F401 — registers every ORM mapper
    from app.database import AsyncSessionLocal, engine

    try:
        async with AsyncSessionLocal() as db:
            done = await upsert_accounts(db, passwords)
    finally:
        await engine.dispose()
    print("==> Contas de validação local: " + ", ".join(done))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_main()))
    except RefusedError as exc:
        print(exc, file=sys.stderr)
        sys.exit(2)
