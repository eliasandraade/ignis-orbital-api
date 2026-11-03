import json
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEV_JWT_SECRET = "dev-secret-change-in-production"
MIN_PRODUCTION_SECRET_LENGTH = 32
# Defaults published in this repo (config, .env.example, docker-compose).
_KNOWN_INSECURE_SECRETS = {
    DEV_JWT_SECRET,
    "your-super-secret-key-change-in-production-never-commit-this",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "IGNIS Orbital API"
    app_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = False

    database_url: str = "postgresql+asyncpg://ignis:ignis_secret@db:5432/ignis_db"

    jwt_secret_key: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 480

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

    @model_validator(mode="after")
    def reject_insecure_production_secret(self) -> "Settings":
        if self.is_production and (
            self.jwt_secret_key in _KNOWN_INSECURE_SECRETS
            or len(self.jwt_secret_key) < MIN_PRODUCTION_SECRET_LENGTH
        ):
            raise ValueError(
                "JWT_SECRET_KEY inseguro para APP_ENV=production: use um valor aleatório "
                f"com pelo menos {MIN_PRODUCTION_SECRET_LENGTH} caracteres."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
