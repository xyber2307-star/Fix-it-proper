"""Unit tests for settings. No loop needed."""

import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for key in (
        "FRONTEND_ORIGIN",
        "GROQ_API_KEY",
        "GROQ_MODEL",
        "PAGESPEED_API_KEY",
        "RATE_LIMIT_PER_HOUR",
        "LOG_LEVEL",
        "USE_PLAYWRIGHT",
        "PLAYWRIGHT_NAVIGATION_TIMEOUT_S",
        "FETCH_CACHE_TTL_SECONDS",
        "FETCH_CACHE_MAX_MB",
        "PROXY_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)


def test_defaults_match_dev_convention(clean_env):
    settings = Settings()
    assert settings.frontend_origin == "http://localhost:5173"
    assert settings.groq_api_key == ""
    assert settings.groq_model == "openai/gpt-oss-120b"
    assert settings.pagespeed_api_key == ""
    assert settings.rate_limit_per_hour == 10
    assert settings.log_level == "INFO"
    assert settings.use_playwright is True
    assert settings.playwright_navigation_timeout_s == 15.0
    assert settings.fetch_cache_ttl_seconds == 3600
    assert settings.fetch_cache_max_mb == 64
    assert settings.proxy_enabled is False


def test_frontend_origin_must_be_http():
    with pytest.raises(ValidationError):
        Settings(frontend_origin="ftp://app.test")
    assert Settings(frontend_origin="https://app.test/").frontend_origin == "https://app.test"


def test_rate_limit_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(rate_limit_per_hour=0)
