"""Demo-account verification procedure (seed/demo_users.py) and admin bootstrap."""

import pytest

from app.core.security import hash_password
from seed.demo_users import (
    DEMO_EMAILS,
    Finding,
    WouldRemoveLastAdminError,
    classify,
    ensure_admin_remains,
)
from seed.seed_users import USERS

DEMO_PW = {u["role"]: u["password"] for u in USERS}


def test_seed_demo_account_with_published_password_is_risky():
    f = classify("1", "admin@ignis-orbital.com", "admin", True, hash_password(DEMO_PW["admin"]))
    assert f.demo_email
    assert f.published_password
    assert f.risky


def test_real_account_reusing_a_published_password_is_flagged():
    f = classify("2", "pessoa@orgao.example", "gestor", True, hash_password(DEMO_PW["gestor"]))
    assert not f.demo_email
    assert f.published_password
    assert f.risky


def test_clean_account_is_not_flagged():
    strong = hash_password("uma-senha-longa-unica")
    f = classify("3", "pessoa@orgao.example", "gestor", True, strong)
    assert not f.risky


def test_inactive_demo_account_is_not_risky():
    f = classify("4", "campo@ibama.gov.br", "campo", False, hash_password(DEMO_PW["campo"]))
    assert f.demo_email
    assert not f.risky


def test_all_seed_emails_are_known():
    assert {"admin@ignis-orbital.com", "gestor@semace.ce.gov.br"} <= DEMO_EMAILS


def _admin(risky: bool) -> Finding:
    return Finding("x", "a@example.org", "admin", True, demo_email=risky, published_password=risky)


def test_deactivation_refused_when_no_legitimate_admin_remains():
    """Codex P1 (PR #3): revoking the only (demo) admin would lock everyone out."""
    findings = [_admin(True)]
    with pytest.raises(WouldRemoveLastAdminError):
        ensure_admin_remains(findings, active_admins=1)


def test_deactivation_allowed_when_a_real_admin_exists():
    ensure_admin_remains([_admin(True)], active_admins=2)


def test_deactivation_of_non_admins_is_always_allowed():
    gestor = Finding("y", "g@example.org", "gestor", True, demo_email=True, published_password=True)
    ensure_admin_remains([gestor], active_admins=0)


def test_bootstrap_rejects_published_or_short_password():
    from pydantic import ValidationError

    from app.users.schemas import UserCreate

    for pw in (DEMO_PW["admin"], "curta"):
        with pytest.raises(ValidationError):
            UserCreate(name="Admin Real", email="admin@orgao.example", password=pw, role="admin")


def test_bootstrap_reads_password_from_stream_not_argv():
    import io

    from seed.bootstrap_admin import read_password

    assert read_password(io.StringIO("uma-senha-longa-unica\n")) == "uma-senha-longa-unica"
