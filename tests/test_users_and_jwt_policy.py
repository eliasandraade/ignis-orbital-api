"""Account creation policy and JWT validation (Sprint 0.1)."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pydantic import ValidationError

from app.core.security import create_access_token, decode_token
from app.users.schemas import UserCreate, UserUpdate
from seed.seed_users import USERS

# Published demo passwords come from the seed itself (no new literals): the
# tests assert that the admin API rejects exactly these values.
DEMO_PW = {u["role"]: u["password"] for u in USERS}

VALID = {
    "name": "Operadora Teste",
    "email": "operadora@example.org",
    "password": "uma-senha-longa-e-unica",
    "role": "gestor",
}


@pytest.mark.parametrize(
    "password",
    [DEMO_PW["admin"], DEMO_PW["gestor"], "curta", DEMO_PW["admin"].upper(), "x" * 73],
)
def test_user_create_rejects_published_short_or_oversized_passwords(password):
    with pytest.raises(ValidationError):
        UserCreate(**{**VALID, "password": password})


def test_user_create_rejects_unknown_role_and_bad_email():
    with pytest.raises(ValidationError):
        UserCreate(**{**VALID, "role": "superadmin"})
    with pytest.raises(ValidationError):
        UserCreate(**{**VALID, "email": "not-an-email"})
    with pytest.raises(ValidationError):
        UserCreate(**{**VALID, "is_admin": True})


def test_user_create_accepts_strong_password():
    assert UserCreate(**VALID).role == "gestor"


def test_user_update_password_policy_applies_only_when_set():
    assert UserUpdate(name="Novo Nome").password is None
    with pytest.raises(ValidationError):
        UserUpdate(password=DEMO_PW["admin"])


async def test_admin_api_rejects_demo_password(client):
    """Integration through the router: validation happens before any DB access."""
    from app.dependencies import get_current_user
    from app.main import app

    admin = type("U", (), {"id": uuid.uuid4(), "name": "a", "role": "admin", "is_active": True})()
    app.dependency_overrides[get_current_user] = lambda: admin
    response = await client.post(
        "/api/v1/admin/users", json={**VALID, "password": DEMO_PW["admin"]}
    )
    assert response.status_code == 422


def test_token_round_trip():
    token = create_access_token(subject="abc", role="gestor")
    assert decode_token(token)["sub"] == "abc"


@pytest.mark.parametrize("missing", ["exp", "iat", "sub"])
def test_token_missing_required_claim_is_rejected(missing):
    from app.core.security import settings

    claims = {
        "sub": "abc",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    claims.pop(missing)
    token = jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_token(token)


def test_unsigned_token_is_rejected():
    token = jwt.encode(
        {"sub": "abc", "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(minutes=5)},
        key=None,
        algorithm="none",
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token)


def test_expired_token_is_rejected():
    from app.core.security import settings

    token = jwt.encode(
        {"sub": "abc", "iat": datetime.now(UTC), "exp": datetime.now(UTC) - timedelta(seconds=1)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token)
