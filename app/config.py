import json
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 480

    # External API base URLs
    open_meteo_base_url: str = "https://api.open-meteo.com/v1"
    nasa_firms_map_key: str = ""
    nasa_firms_base_url: str = "https://firms.modaps.eosdis.nasa.gov/api"
    osm_nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    external_api_timeout_seconds: int = 10
    external_api_cache_ttl_minutes: int = 60

    cors_origins: list[str] = [
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
