"""Backend settings loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Settings(BaseSettings):
    """All backend configuration comes from the environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    frontend_origin: str = "http://localhost:5173"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    pagespeed_api_key: str = ""
    rate_limit_per_hour: int = Field(default=10, ge=1)
    log_level: LogLevel = "INFO"
    use_playwright: bool = True
    playwright_navigation_timeout_s: float = Field(default=15.0, gt=0)
    fetch_cache_ttl_seconds: int = Field(default=3600, ge=60)
    fetch_cache_max_mb: int = Field(default=64, ge=1)
    # Reserved for later. Proxies are not used in v1.
    proxy_enabled: bool = False
    firebase_project_id: str = ""
    firebase_credentials_path: str = ""
    firebase_credentials_base64: str = ""
    firestore_emulator_host: str = ""
    firebase_auth_emulator_host: str = ""
    report_retention_days: int = Field(default=30, ge=1)
    contact_rate_limit_per_hour: int = Field(default=5, ge=1)

    @field_validator("frontend_origin")
    @classmethod
    def _origin_must_be_http(cls, value: str) -> str:
        lowered = value.lower()
        if not (lowered.startswith("http://") or lowered.startswith("https://")):
            raise ValueError("FRONTEND_ORIGIN must start with http:// or https://")
        return value.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    """Return cached settings built from the current environment."""
    return Settings()
