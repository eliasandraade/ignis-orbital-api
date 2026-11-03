"""Find (and optionally deactivate) accounts that use demo e-mails or published passwords.

Read-only check (safe anywhere):

    python -m seed.demo_users check

Deactivation (requires explicit confirmation of the database host):

    python -m seed.demo_users deactivate --confirm-host <host-of-DATABASE_URL>

Deactivation sets is_active=false, replaces the password hash with a random,
unknown value (reactivation requires a password reset by an admin) and writes
an audit log entry per account. It never deletes rows and never prints password
hashes or secrets. Exit code of `check`: 0 = clean, 4 = risky accounts found
(2 is reserved for argparse usage errors). Exit code of `deactivate`: 3 = refused
because no legitimate admin would remain (create one with seed.bootstrap_admin).

Running this against production requires the owner's authorization
(see docs/IGNIS/RAILWAY-RECOVERY.md).
"""

import argparse
import asyncio
import secrets
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.passwords import PUBLISHED_PASSWORDS
from app.core.security import hash_password, verify_password
from seed.seed_users import USERS

EXIT_RISKY = 4
EXIT_LAST_ADMIN = 3

DEMO_EMAILS = frozenset(u["email"].lower() for u in USERS)
_KNOWN_PASSWORDS = frozenset({u["password"] for u in USERS} | PUBLISHED_PASSWORDS)


class WouldRemoveLastAdminError(RuntimeError):
    """Deactivation would leave no legitimate active administrator."""


@dataclass(frozen=True)
class Finding:
    user_id: str
    email: str
    role: str
    is_active: bool
    demo_email: bool
    published_password: bool

    @property
    def risky(self) -> bool:
        # A published password is risky even on an inactive account: an admin can
        # reactivate it (PATCH is_active=true) and the credential works again.
        return self.published_password or (self.is_active and self.demo_email)


def _matches(password: str, password_hash: str) -> bool:
    try:
        return verify_password(password, password_hash)
    except (ValueError, TypeError):
        # Malformed/unknown hash: cannot match a published password; a single
        # bad row must not abort the whole scan.
        return False


def classify(user_id: str, email: str, role: str, is_active: bool, password_hash: str) -> Finding:
    published = any(_matches(p, password_hash) for p in _KNOWN_PASSWORDS)
    return Finding(
        user_id=user_id,
        email=email,
        role=role,
        is_active=is_active,
        demo_email=email.lower() in DEMO_EMAILS,
        published_password=published,
    )


async def scan(db: AsyncSession) -> list[Finding]:
    from app.users.model import User

    users = (await db.execute(select(User))).scalars().all()
    findings = [classify(str(u.id), u.email, u.role, u.is_active, u.password_hash) for u in users]
    return [f for f in findings if f.demo_email or f.published_password]


def ensure_admin_remains(findings: list[Finding], active_admins: int) -> None:
    """Refuse when every active administrator is about to be revoked."""
    revoked_admins = sum(1 for f in findings if f.risky and f.is_active and f.role == "admin")
    if revoked_admins and active_admins - revoked_admins < 1:
        raise WouldRemoveLastAdminError(
            "Recusado: a desativação deixaria o sistema sem administrador ativo. "
            "Crie um administrador real antes: python -m seed.bootstrap_admin "
            "--email <e-mail> --name <nome> (senha via stdin)."
        )


async def deactivate(db: AsyncSession, findings: list[Finding]) -> int:
    from sqlalchemy import func

    from app.core.audit import log_action
    from app.users.model import User

    active_admins = await db.scalar(
        select(func.count()).select_from(User).where(User.role == "admin", User.is_active)
    )
    ensure_admin_remains(findings, int(active_admins or 0))

    count = 0
    for f in findings:
        if not f.risky:
            continue
        user = await db.get(User, f.user_id)
        user.is_active = False
        user.password_hash = hash_password(secrets.token_urlsafe(32))
        await log_action(
            db,
            "user.demo_credentials_revoked",
            "User",
            f.user_id,
            actor_name="ops:seed.demo_users",
            metadata={"demo_email": f.demo_email, "published_password": f.published_password},
        )
        count += 1
    await db.commit()
    return count


def _db_host() -> str:
    from app.config import get_settings

    return urlsplit(get_settings().database_url.replace("+asyncpg", "")).hostname or ""


def _print(findings: list[Finding]) -> None:
    if not findings:
        print("Nenhuma conta com e-mail demonstrativo ou senha publicada.")
        return
    print(f"{'email':45} {'papel':8} {'ativa':6} {'e-mail demo':12} senha publicada")
    for f in findings:
        print(
            f"{f.email:45} {f.role:8} {str(f.is_active):6} "
            f"{str(f.demo_email):12} {f.published_password}"
        )


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m seed.demo_users")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    d = sub.add_parser("deactivate")
    d.add_argument("--confirm-host", required=True, help="host do DATABASE_URL alvo")
    args = parser.parse_args(argv)

    import app.main  # noqa: F401 — registers every ORM mapper (FKs between models)
    from app.database import AsyncSessionLocal

    host = _db_host()
    print(f"Banco alvo: host={host}")
    async with AsyncSessionLocal() as db:
        findings = await scan(db)
        _print(findings)
        if args.cmd == "check":
            return EXIT_RISKY if any(f.risky for f in findings) else 0
        if args.confirm_host != host:
            print(f"Recusado: --confirm-host={args.confirm_host!r} difere do host alvo {host!r}.")
            return 1
        try:
            n = await deactivate(db, findings)
        except WouldRemoveLastAdminError as exc:
            print(exc)
            return EXIT_LAST_ADMIN
        print(f"{n} conta(s) desativada(s) e com senha invalidada.")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
