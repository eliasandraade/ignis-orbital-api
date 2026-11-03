"""Demo-account verification procedure (seed/demo_users.py)."""

from app.core.security import hash_password
from seed.demo_users import DEMO_EMAILS, classify


def test_seed_demo_account_with_published_password_is_risky():
    f = classify("1", "admin@ignis-orbital.com", "admin", True, hash_password("admin@123"))
    assert f.demo_email and f.published_password and f.risky


def test_real_account_reusing_a_published_password_is_flagged():
    f = classify("2", "pessoa@orgao.example", "gestor", True, hash_password("gestor@123"))
    assert not f.demo_email
    assert f.published_password and f.risky


def test_clean_account_is_not_flagged():
    strong = hash_password("uma-senha-longa-unica")
    f = classify("3", "pessoa@orgao.example", "gestor", True, strong)
    assert not f.risky


def test_inactive_demo_account_is_not_risky():
    f = classify("4", "campo@ibama.gov.br", "campo", False, hash_password("campo@123"))
    assert f.demo_email and not f.risky


def test_all_seed_emails_are_known():
    assert {"admin@ignis-orbital.com", "gestor@semace.ce.gov.br"} <= DEMO_EMAILS
