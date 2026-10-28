"""Application settings, loaded once from environment variables / backend/.env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str
    test_database_url: str | None = None

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120

    # Kept as a plain comma-separated string so it reads naturally in .env
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    # Cached so .env is parsed once; a missing required variable fails fast at startup.
    return Settings()
