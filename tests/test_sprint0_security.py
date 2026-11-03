"""Sprint 0 security controls: production secrets, demo seed, readiness,
public report validation and rate limiting."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.config import Settings
from app.core import rate_limit as rl
from app.database import get_db
from app.main import app
from app.reports.schemas import ReportCreate
from seed.seed_all import DemoSeedRefusedError, ensure_seed_allowed

STRONG_SECRET = "x" * 48

# --- JWT secret guard ---------------------------------------------------------------


@pytest.mark.parametrize(
    "secret",
    [
        "dev-secret-change-in-production",
        "your-super-secret-key-change-in-production-never-commit-this",
        "short-secret",
    ],
)
def test_production_rejects_insecure_jwt_secret(secret):
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(app_env="production", jwt_secret_key=secret, _env_file=None)


def test_production_accepts_strong_jwt_secret():
    settings = Settings(app_env="production", jwt_secret_key=STRONG_SECRET, _env_file=None)
    assert settings.is_production


def test_development_keeps_dev_default():
    settings = Settings(app_env="development", _env_file=None)
    assert settings.jwt_secret_key == "dev-secret-change-in-production"


@pytest.mark.parametrize(
    "raw",
    [
        "http://localhost:8080,https://ignis.example.org",
        '["http://localhost:8080", "https://ignis.example.org"]',
    ],
)
def test_cors_origins_accepts_documented_env_formats(monkeypatch, raw):
    """Regression: the comma-separated format from .env.example crashed at boot."""
    monkeypatch.setenv("CORS_ORIGINS", raw)
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:8080", "https://ignis.example.org"]


def test_demo_modes_are_off_by_default():
    settings = Settings(_env_file=None)
    assert settings.orbital_alerts_demo_mode is False
    assert settings.trust_proxy_headers is False


# --- demo seed guard ---------------------------------------------------------------


def _patch_env(monkeypatch, app_env: str):
    from seed import seed_all

    fake = MagicMock()
    fake.is_production = app_env == "production"
    monkeypatch.setattr(seed_all, "get_settings", lambda: fake)


def test_demo_seed_refused_in_production(monkeypatch):
    _patch_env(monkeypatch, "production")
    monkeypatch.delenv("SEED_DEMO_DATA", raising=False)
    with pytest.raises(DemoSeedRefusedError):
        ensure_seed_allowed()


def test_demo_seed_allowed_in_production_only_with_explicit_opt_in(monkeypatch):
    _patch_env(monkeypatch, "production")
    monkeypatch.setenv("SEED_DEMO_DATA", "true")
    ensure_seed_allowed()


def test_demo_seed_allowed_outside_production(monkeypatch):
    _patch_env(monkeypatch, "development")
    monkeypatch.delenv("SEED_DEMO_DATA", raising=False)
    ensure_seed_allowed()


# --- readiness does not leak driver errors -------------------------------------------


async def test_ready_hides_database_error_details(client):
    async def _db():
        session = AsyncMock()
        session.execute.side_effect = Exception(
            "connection to postgresql://ignis:SECRETPWD@db.internal:5432 failed"
        )
        yield session

    app.dependency_overrides[get_db] = _db
    response = await client.get("/ready")
    assert response.status_code == 503
    assert "SECRETPWD" not in response.text
    assert "db.internal" not in response.text
    assert response.json()["detail"] == {"status": "unavailable", "database": "unreachable"}


# --- public report validation ---------------------------------------------------------

VALID_REPORT = {
    "type": "fire",
    "description": "Fumaça intensa próxima à margem do rio",
    "urgency": "high",
    "latitude": -4.2,
    "longitude": -38.5,
}


def test_anonymous_report_drops_identifying_fields():
    report = ReportCreate(
        **VALID_REPORT, is_anonymous=True, reporter_name="Fulano", contact="85 99999-0000"
    )
    assert report.reporter_name is None
    assert report.contact is None


@pytest.mark.parametrize(
    "override",
    [
        {"latitude": 95.0},
        {"longitude": -200.0},
        {"latitude": None},  # longitude without latitude
        {"description": "curta"},
        {"description": "x" * 4001},
        {"reporter_name": "n" * 256},
        {"evidence_urls": ["javascript:alert(1)"]},
        {"evidence_urls": [f"https://ex.com/{i}.jpg" for i in range(11)]},
        {"is_admin": True},  # unknown fields are rejected
    ],
)
def test_report_rejects_invalid_input(override):
    with pytest.raises(ValidationError):
        ReportCreate(**{**VALID_REPORT, **override})


def test_report_accepts_frontend_payload_shape():
    # Same keys the public form sends (ApiReportCreate in ignis-fire-watch).
    report = ReportCreate(
        **VALID_REPORT,
        protected_area_id=None,
        reporter_name=None,
        contact=None,
        is_anonymous=False,
    )
    assert report.evidence_url_strings == []


async def test_report_endpoint_returns_422_for_invalid_coordinates(client):
    response = await client.post("/api/v1/reports", json={**VALID_REPORT, "latitude": 300})
    assert response.status_code == 422


# --- rate limiting ---------------------------------------------------------------------


async def test_login_is_rate_limited(client):
    payload = {"email": "nobody@example.com", "password": "wrong"}

    async def _db():
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result
        yield session

    app.dependency_overrides[get_db] = _db
    statuses = [
        (await client.post("/api/v1/auth/login", json=payload)).status_code for _ in range(11)
    ]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429


async def test_public_report_submission_is_rate_limited(client):
    # Invalid payloads still count: the limiter runs before validation-heavy work.
    statuses = [
        (await client.post("/api/v1/reports", json={"type": "fire"})).status_code
        for _ in range(11)
    ]
    assert statuses[-1] == 429


def _request(client_host: str, xff: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "headers": headers, "client": (client_host, 1234)})


def test_client_ip_ignores_forwarded_header_by_default():
    assert rl.client_ip(_request("10.0.0.1", "1.2.3.4")) == "10.0.0.1"


def test_client_ip_uses_rightmost_forwarded_entry_when_trusted(monkeypatch):
    monkeypatch.setattr(rl.get_settings(), "trust_proxy_headers", True)
    assert rl.client_ip(_request("10.0.0.1", "6.6.6.6, 1.2.3.4")) == "1.2.3.4"


def test_rate_limit_window_resets():
    assert rl._hit("k", limit=1, window_seconds=60, now=0.0) is None
    assert rl._hit("k", limit=1, window_seconds=60, now=1.0) is not None
    assert rl._hit("k", limit=1, window_seconds=60, now=61.0) is None
