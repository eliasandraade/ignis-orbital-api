"""Sprint 0 security controls: production secrets, demo seed, readiness,
public report validation and rate limiting."""

import pathlib
import secrets
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

# Generated per run: a random secret, never a literal in the repository.
STRONG_SECRET = secrets.token_hex(32)
PROD_DB = "postgresql+asyncpg://app:not-a-real-password@db.internal:5432/ignis"
WEB_ORIGIN = "https://ignis-web-staging.up.railway.app"
# Minimal valid configuration for an operational environment.
OPERATIONAL = {
    "jwt_secret_key": STRONG_SECRET,
    "database_url": PROD_DB,
    "cors_origins": [WEB_ORIGIN],
}

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
        Settings(app_env="production", jwt_secret_key=secret, database_url=PROD_DB, _env_file=None)


def test_production_accepts_strong_jwt_secret():
    settings = Settings(app_env="production", **OPERATIONAL, _env_file=None)
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
    # Sprint 1.3: the orbital demo mode no longer exists (alerts come from PostGIS).
    assert not hasattr(settings, "orbital_alerts_demo_mode")
    assert settings.trust_proxy_headers is False


# --- demo seed guard ---------------------------------------------------------------


def _patch_env(monkeypatch, app_env: str):
    from seed import seed_all

    settings = Settings(app_env=app_env, **OPERATIONAL, _env_file=None)
    monkeypatch.setattr(seed_all, "get_settings", lambda: settings)


@pytest.mark.parametrize("app_env", ["production", "staging"])
def test_demo_seed_refused_in_operational_envs(monkeypatch, app_env):
    _patch_env(monkeypatch, app_env)
    with pytest.raises(DemoSeedRefusedError):
        ensure_seed_allowed()


@pytest.mark.parametrize("app_env", ["production", "staging"])
def test_demo_seed_has_no_override_in_operational_envs(monkeypatch, app_env):
    """Codex P1 follow-up: the old SEED_DEMO_DATA=true override was removed."""
    monkeypatch.setenv("SEED_DEMO_DATA", "true")
    _patch_env(monkeypatch, app_env)
    with pytest.raises(DemoSeedRefusedError):
        ensure_seed_allowed()


@pytest.mark.parametrize("app_env", ["development", "test", "demo"])
def test_demo_seed_allowed_in_demo_envs(monkeypatch, app_env):
    _patch_env(monkeypatch, app_env)
    ensure_seed_allowed()


# --- real dotenv files (Codex P1 on PR #3) ---------------------------------------------


def _load_dotenv(tmp_path, monkeypatch, content: str) -> Settings:
    env_file = tmp_path / ".env"
    env_file.write_text(content, encoding="utf-8")
    # Make sure nothing comes from the process environment.
    for key in ("APP_ENV", "SEED_DEMO_DATA", "JWT_SECRET_KEY", "DATABASE_URL", "CORS_ORIGINS"):
        monkeypatch.delenv(key, raising=False)
    return Settings(_env_file=str(env_file))


@pytest.mark.parametrize("seed_value", ["false", "true"])
def test_dotenv_with_seed_demo_data_loads(tmp_path, monkeypatch, seed_value):
    """A legacy SEED_DEMO_DATA line in .env must not abort startup (was extra_forbidden)
    and must never enable the seed in an operational environment."""
    settings = _load_dotenv(
        tmp_path,
        monkeypatch,
        f"APP_ENV=production\nJWT_SECRET_KEY={STRONG_SECRET}\nDATABASE_URL={PROD_DB}\n"
        f"CORS_ORIGINS={WEB_ORIGIN}\nSEED_DEMO_DATA={seed_value}\n",
    )
    assert settings.app_env == "production"
    assert settings.demo_seed_allowed is False


def test_env_example_file_loads_as_dotenv(tmp_path, monkeypatch):
    """`cp .env.example .env` is the documented setup; it must load (POSTGRES_* included)."""
    example = (pathlib.Path(__file__).parent.parent / ".env.example").read_text(encoding="utf-8")
    settings = _load_dotenv(tmp_path, monkeypatch, example)
    assert settings.app_env == "development"
    assert settings.demo_seed_allowed is True
    assert "http://localhost:5173" in settings.cors_origins


@pytest.mark.parametrize("bad_env", ["prod", "Production ", "live", ""])
def test_invalid_app_env_fails_closed(tmp_path, monkeypatch, bad_env):
    with pytest.raises(ValidationError):
        _load_dotenv(tmp_path, monkeypatch, f"APP_ENV={bad_env}\n")


def test_operational_env_rejects_missing_or_published_database_url(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        _load_dotenv(tmp_path, monkeypatch, f"APP_ENV=production\nJWT_SECRET_KEY={STRONG_SECRET}\n")


def test_staging_also_requires_strong_secret(tmp_path, monkeypatch):
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        _load_dotenv(tmp_path, monkeypatch, "APP_ENV=staging\n")


@pytest.mark.parametrize("alg", ["none", "RS256", "hs256x"])
def test_jwt_algorithm_restricted_to_hmac(alg):
    with pytest.raises(ValidationError):
        Settings(jwt_algorithm=alg, _env_file=None)


def test_entrypoint_requires_explicit_app_env_and_skips_seed_safely():
    script = (pathlib.Path(__file__).parent.parent / "scripts" / "entrypoint.sh").read_text()
    assert ': "${APP_ENV:?' in script
    assert "python -m seed --if-allowed" in script
    # Railway pre-deploy runs only the migrate role; the API role can skip migrations.
    assert "migrate)" in script
    assert "MIGRATE_ON_START:-true" in script
    assert "SEED_DEMO_DATA" not in script
    # The local validation stack may skip the demo seed; nothing may force it.
    assert 'SKIP_DEMO_SEED:-false}" == "true"' in script


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
        session.scalar = AsyncMock(return_value=None)
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
        (await client.post("/api/v1/reports", json={"type": "fire"})).status_code for _ in range(11)
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


# --- independent review follow-up (Sprint 0.1) -----------------------------------------


@pytest.mark.parametrize(
    "secret",
    [
        "x" * 48,  # repetitive
        " " * 40,  # whitespace
        " " + secrets.token_hex(32),  # padded
        "dev-secret-change-in-production!",  # published value with a suffix
    ],
)
def test_operational_rejects_trivial_or_derived_jwt_secrets(secret):
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        Settings(app_env="production", jwt_secret_key=secret, database_url=PROD_DB, _env_file=None)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "postgresql+asyncpg://ignis@localhost/ignis_db",  # dev variant without port
        "postgresql+asyncpg://app@db.internal:5432/ignis",  # no password
        "postgresql+asyncpg://ignis:ignis_secret@db.internal:5432/ignis",  # published
    ],
)
def test_operational_rejects_unsafe_database_urls(url):
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(
            app_env="production", jwt_secret_key=STRONG_SECRET, database_url=url, _env_file=None
        )


# --- Railway deployment (Railway-only hosting) ------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "postgresql://u:p@postgis.railway.internal:5432/ignis",
            "postgresql+asyncpg://u:p@postgis.railway.internal:5432/ignis",
        ),
        ("postgres://u:p@h:5432/db", "postgresql+asyncpg://u:p@h:5432/db"),
        ("postgresql://u:p@h/db?sslmode=require", "postgresql+asyncpg://u:p@h/db?ssl=require"),
        ("postgresql+asyncpg://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
    ],
)
def test_database_url_from_railway_uses_async_driver(raw, expected):
    assert Settings(database_url=raw, _env_file=None).database_url == expected


@pytest.mark.parametrize(
    "origins",
    [
        [],
        ["*"],
        ["http://ignis-web.up.railway.app"],
        ["http://localhost:8080"],
        ["https://localhost:8080"],
        [WEB_ORIGIN, "https://*.up.railway.app"],
        [WEB_ORIGIN + "/app"],
    ],
)
@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_operational_cors_requires_explicit_https_origins(app_env, origins):
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(app_env=app_env, **{**OPERATIONAL, "cors_origins": origins}, _env_file=None)


def test_operational_cors_accepts_railway_domain_from_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", f"{WEB_ORIGIN}, https://ignis.example.org")
    settings = Settings(
        app_env="staging", jwt_secret_key=STRONG_SECRET, database_url=PROD_DB, _env_file=None
    )
    assert settings.cors_origins == [WEB_ORIGIN, "https://ignis.example.org"]


def test_default_cors_has_no_hosted_origin():
    """Railway-only: no third-party hosting domain is trusted by default."""
    assert Settings(_env_file=None).cors_origins == [
        "http://localhost:8080",
        "http://localhost:5173",
    ]


@pytest.mark.parametrize(
    ("railway_env", "app_env"),
    [("staging", "production"), ("production", "staging"), ("ignis-pr-7", "production")],
)
def test_railway_environment_mismatch_refuses_to_boot(railway_env, app_env):
    with pytest.raises(ValidationError, match="ambiente Railway"):
        Settings(
            app_env=app_env, RAILWAY_ENVIRONMENT_NAME=railway_env, **OPERATIONAL, _env_file=None
        )


@pytest.mark.parametrize(
    ("railway_env", "app_env"),
    [
        ("staging", "staging"),
        ("production", "production"),
        ("Production", "production"),
        ("ignis-pr-7", "staging"),
        ("", "production"),
    ],
)
def test_railway_environment_match_boots(railway_env, app_env):
    settings = Settings(
        app_env=app_env, RAILWAY_ENVIRONMENT_NAME=railway_env, **OPERATIONAL, _env_file=None
    )
    assert settings.app_env == app_env


def test_railway_environment_name_read_from_process_env(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "production")
    with pytest.raises(ValidationError, match="ambiente Railway"):
        Settings(app_env="staging", **OPERATIONAL, _env_file=None)


def _request_with(client_host: str, headers: dict[str, str]) -> Request:
    raw = [(k.encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": (client_host, 1234)})


def test_client_ip_uses_x_real_ip_on_railway(monkeypatch):
    settings = rl.get_settings()
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    monkeypatch.setattr(settings, "client_ip_header", "x-real-ip")
    # The rightmost X-Forwarded-For hop can be a Railway proxy shared by everyone.
    headers = {"x-real-ip": "203.0.113.9", "x-forwarded-for": "203.0.113.9, 100.64.0.7"}
    req = _request_with("100.64.0.2", headers)
    assert rl.client_ip(req) == "203.0.113.9"


def test_client_ip_x_real_ip_ignored_unless_trusted(monkeypatch):
    monkeypatch.setattr(rl.get_settings(), "client_ip_header", "x-real-ip")
    assert rl.client_ip(_request_with("100.64.0.2", {"x-real-ip": "6.6.6.6"})) == "100.64.0.2"


def test_client_ip_header_is_a_closed_set():
    with pytest.raises(ValidationError):
        Settings(client_ip_header="x-client-ip", _env_file=None)


def test_configuration_errors_never_echo_secrets():
    """A rejected configuration ends up in deploy logs: no input values in the error."""
    jwt = secrets.token_hex(32)
    db_password = secrets.token_hex(16)
    with pytest.raises(ValidationError) as exc:
        Settings(
            app_env="staging",
            jwt_secret_key=jwt,
            database_url=f"postgresql://ignis:{db_password}@ignis-postgis.railway.internal:5432/ignis",
            cors_origins="https://",
        )
    text = str(exc.value)
    assert "CORS_ORIGINS" in text
    assert jwt not in text
    assert db_password not in text
    assert "input_value" not in text
