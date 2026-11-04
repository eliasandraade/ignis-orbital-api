"""Local human-validation accounts: refused outside a local stack, idempotent inside."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from seed import validation_accounts as va


@pytest.mark.parametrize(
    "environ",
    [
        {"APP_ENV": "production"},
        {"APP_ENV": "staging"},
        {"APP_ENV": "demo"},
        {},
        {"APP_ENV": "development", "RAILWAY_ENVIRONMENT_NAME": "staging"},
        {"APP_ENV": "test", "RAILWAY_PROJECT_ID": "x"},
    ],
)
def test_refuses_anything_but_a_local_stack(environ):
    with pytest.raises(va.RefusedError):
        va.ensure_local_environment(environ)


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_accepts_local_environments(app_env):
    va.ensure_local_environment({"APP_ENV": app_env})


async def test_accounts_are_idempotent_audited_and_policy_checked(geo_engine):
    import app.main  # noqa: F401
    from app.core.security import verify_password

    passwords = {"admin": "Adm-local-teste-123-9", "gestor": "Ges-local-teste-123-9"}
    async with AsyncSession(geo_engine) as db:
        assert len(await va.upsert_accounts(db, passwords)) == 2
    rotated = {"admin": "Adm-outra-senha-456-9"}
    async with AsyncSession(geo_engine) as db:
        assert await va.upsert_accounts(db, rotated) == ["admin.validacao@example.org"]
    async with geo_engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT email, role, password_hash FROM users"
                    " WHERE email LIKE '%.validacao@example.org' ORDER BY email"
                )
            )
        ).all()
        audits = await conn.scalar(
            text("SELECT count(*) FROM audit_logs WHERE action = 'user.local_validation_account'")
        )
    assert [(r.email, r.role) for r in rows] == [
        ("admin.validacao@example.org", "admin"),
        ("gestor.validacao@example.org", "gestor"),
    ]
    assert verify_password(rotated["admin"], rows[0].password_hash)
    assert audits == 3
    async with AsyncSession(geo_engine) as db:
        with pytest.raises(ValueError):  # the API's password policy applies
            await va.upsert_accounts(db, {"gestor": "curta"})
    async with geo_engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM audit_logs WHERE action = 'user.local_validation_account'")
        )
        await conn.execute(text("DELETE FROM users WHERE email LIKE '%.validacao@example.org'"))
