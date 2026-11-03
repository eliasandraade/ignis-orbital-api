import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEV_JWT_SECRET = "dev-secret-change-in-production"
# Local-development placeholder only. It carries no credentials (local setups
# pass DATABASE_URL via docker compose or .env) and is REJECTED at boot in
# staging/production (reject_insecure_operational_secret, covered by
# tests/test_sprint0_security.py) — so the "passwordless database" finding does
# not apply to any operational deployment.
DEV_DATABASE_URL = "postgresql+asyncpg://ignis@localhost:5432/ignis_db"  # NOSONAR python:S2115
MIN_PRODUCTION_SECRET_LENGTH = 32
# Defaults published in this repo (config, .env.example, docker-compose).
_KNOWN_INSECURE_SECRETS = {
    DEV_JWT_SECRET,
    "your-super-secret-key-change-in-production-never-commit-this",
}


def _weak_secret(secret: str) -> bool:
    """Length alone is not enough: reject padded/repetitive or published values."""
    return (
        len(secret) < MIN_PRODUCTION_SECRET_LENGTH
        or secret != secret.strip()
        or len(set(secret)) < 10
        or any(known in secret for known in _KNOWN_INSECURE_SECRETS)
    )


def _unsafe_database_url(url: str) -> bool:
    """Operational DB URLs must be explicit and carry a non-published password."""
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
        password = parts.password
    except ValueError:
        return True
    return (
        url == DEV_DATABASE_URL
        or not parts.hostname
        or not password
        or password == "ignis_secret"  # published in docker-compose/.env.example
    )


AppEnv = Literal["development", "test", "demo", "staging", "production"]

# Operational environments: no demo data, no published credentials, strong secrets.
OPERATIONAL_ENVS: frozenset[str] = frozenset({"staging", "production"})
# The demo seed (users with published passwords) may only run here.
DEMO_SEED_ENVS: frozenset[str] = frozenset({"development", "test", "demo"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # .env is shared with docker compose (POSTGRES_*), so unrelated keys
        # must not abort startup. Unknown keys are ignored, never applied.
        extra="ignore",
    )

    app_name: str = "IGNIS Orbital API"
    app_version: str = "0.1.0"
    # Closed set: a typo such as APP_ENV=prod must fail, not silently become a
    # non-operational environment where demo data is allowed.
    app_env: AppEnv = "development"
    debug: bool = False

    database_url: str = DEV_DATABASE_URL

    jwt_secret_key: str = DEV_JWT_SECRET
    # HMAC family only: an env value such as "none" must never be accepted.
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_access_token_expire_minutes: int = Field(default=480, ge=5, le=1440)

    # Fictitious orbital alerts are served only when explicitly enabled.
    orbital_alerts_demo_mode: bool = False

    # Rate limiting (in-memory, per process). When behind a trusted reverse
    # proxy (Railway), take the client IP from the rightmost X-Forwarded-For.
    rate_limit_enabled: bool = True
    trust_proxy_headers: bool = False

    # External API base URLs
    open_meteo_base_url: str = "https://api.open-meteo.com/v1"
    nasa_firms_map_key: str = ""
    nasa_firms_base_url: str = "https://firms.modaps.eosdis.nasa.gov/api"
    osm_nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    external_api_timeout_seconds: int = 10
    external_api_cache_ttl_minutes: int = 60

    # NoDecode: without it pydantic-settings JSON-decodes the env value before the
    # validator runs, so the documented comma-separated format crashed at boot.
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:8080",
        "http://localhost:5173",
        "https://ignis-fire-watch-main.vercel.app",
        "https://ignis-fire-watch.vercel.app",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            stripped = v.strip()
            # Accept JSON array: '["http://...", "https://..."]'
            if stripped.startswith("["):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    pass
            # Accept comma-separated: 'http://..., https://...'
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_operational(self) -> bool:
        return self.app_env in OPERATIONAL_ENVS

    @property
    def demo_seed_allowed(self) -> bool:
        """Demo data never runs in staging/production; there is no override."""
        return self.app_env in DEMO_SEED_ENVS

    @model_validator(mode="after")
    def reject_insecure_operational_secret(self) -> "Settings":
        if self.is_operational and _weak_secret(self.jwt_secret_key):
            raise ValueError(
                f"JWT_SECRET_KEY inseguro para APP_ENV={self.app_env}: use um valor aleatório "
                f"com pelo menos {MIN_PRODUCTION_SECRET_LENGTH} caracteres."
            )
        if self.is_operational and _unsafe_database_url(self.database_url):
            raise ValueError(
                f"DATABASE_URL ausente ou com a credencial de desenvolvimento publicada "
                f"(APP_ENV={self.app_env})."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
