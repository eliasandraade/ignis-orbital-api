import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.security import hash_password
from app.database import get_db
from app.main import app

# Usuário fake para testes
FAKE_USER_ID = uuid.uuid4()
FAKE_USER_EMAIL = "gestor@test.com"
FAKE_USER_PASSWORD = "senha123"


def make_fake_user(role="gestor"):
    import datetime

    user = MagicMock()
    user.id = FAKE_USER_ID
    user.name = "Gestor Test"
    user.email = FAKE_USER_EMAIL
    user.password_hash = hash_password(FAKE_USER_PASSWORD)
    user.role = role
    user.team_id = None
    user.is_active = True
    user.created_at = datetime.datetime.now(datetime.UTC)
    user.updated_at = user.created_at
    return user


@pytest.fixture
async def db_with_user():
    """Mock de AsyncSession que retorna um usuário fake no login."""
    mock_db = AsyncMock()
    fake_user = make_fake_user()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = fake_user
    mock_db.execute.return_value = mock_result
    mock_db.commit = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    yield mock_db
    app.dependency_overrides.clear()


@pytest.fixture
async def db_empty():
    """Mock de AsyncSession que retorna None em qualquer select."""
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    mock_db.commit = AsyncMock()

    async def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    yield mock_db
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_login_valid(client, db_with_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": FAKE_USER_EMAIL,
            "password": FAKE_USER_PASSWORD,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "expires_in" in data
    assert data["user"]["role"] == "gestor"


@pytest.mark.asyncio
async def test_login_wrong_password(client, db_with_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": FAKE_USER_EMAIL,
            "password": "senha_errada",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_user_not_found(client, db_empty):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "nao_existe@test.com",
            "password": "qualquer",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_requires_auth(client):
    response = await client.get("/api/v1/auth/me")
    # FastAPI 0.136+ HTTPBearer returns 401 when no Authorization header is present
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_me_with_valid_token(client, db_with_user):
    from app.core.security import create_access_token

    token = create_access_token(str(FAKE_USER_ID), "gestor")
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == FAKE_USER_EMAIL


@pytest.mark.asyncio
async def test_admin_users_requires_admin_role(client, db_with_user):
    from app.core.security import create_access_token

    # token com role gestor (não admin)
    token = create_access_token(str(FAKE_USER_ID), "gestor")
    response = await client.get(
        "/api/v1/admin/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
