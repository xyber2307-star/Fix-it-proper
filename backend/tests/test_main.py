"""Tests for routes, CORS, rate limiting, and error shapes."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Route

from app.config import Settings
from app.fetcher.models import FetchError
from app.main import create_app
from app.schemas import AnalyzeResponse

PUBLIC_IP = "93.184.216.34"
ERROR_KEYS = {"code", "message", "retryable"}
FIXTURES = Path(__file__).parent / "fixtures"


def _full_response() -> AnalyzeResponse:
    data: dict[str, Any] = json.loads((FIXTURES / "full_success.json").read_text(encoding="utf-8"))
    return AnalyzeResponse.model_validate(data)


def _mock_run_analysis(
    monkeypatch: pytest.MonkeyPatch, behavior: AnalyzeResponse | Exception
) -> None:
    async def fake_run_analysis(raw_url: str, **kwargs: Any) -> AnalyzeResponse:
        if isinstance(behavior, Exception):
            raise behavior
        return behavior

    monkeypatch.setattr("app.main.run_analysis", fake_run_analysis)


@pytest.fixture
def app_settings():
    return Settings(frontend_origin="https://app.test", rate_limit_per_hour=10, log_level="WARNING")


@pytest.fixture
def client(app_settings, require_loop):
    return TestClient(create_app(app_settings))


def test_health_ok_and_request_id(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"]


def test_request_id_is_echod_when_sane_and_replaced_when_not(client):
    echoed = client.get("/api/health", headers={"X-Request-ID": "abc-123"})
    assert echoed.headers["X-Request-ID"] == "abc-123"
    replaced = client.get("/api/health", headers={"X-Request-ID": "<bad id>"})
    assert replaced.headers["X-Request-ID"] != "<bad id>"


def test_unknown_route_returns_error_shape(client):
    response = client.get("/nope")
    assert response.status_code == 404
    body = response.json()
    assert set(body.keys()) == ERROR_KEYS
    assert body["code"] == "NOT_FOUND"
    assert body["retryable"] is False


def test_docs_are_disabled(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_wrong_method_returns_error_shape(client):
    response = client.get("/api/analyze")
    assert response.status_code == 405
    assert response.json()["code"] == "METHOD_NOT_ALLOWED"


def test_analyze_rejects_invalid_url_with_contract_shape(client):
    response = client.post("/api/analyze", json={"url": "not-a-url"})
    assert response.status_code == 422
    body = response.json()
    assert set(body.keys()) == ERROR_KEYS
    assert body == {
        "code": "INVALID_URL",
        "message": "URL must start with http:// or https://.",
        "retryable": False,
    }


def test_analyze_rejects_missing_url_field(client):
    response = client.post("/api/analyze", json={})
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


def test_analyze_blocks_private_ip_with_contract_shape(client):
    response = client.post("/api/analyze", json={"url": "http://127.0.0.1/"})
    assert response.status_code == 400
    body = response.json()
    assert set(body.keys()) == ERROR_KEYS
    assert body["code"] == "URL_BLOCKED"
    assert body["retryable"] is False


def test_analyze_returns_contract_response(client, monkeypatch):
    _mock_run_analysis(monkeypatch, _full_response())
    response = client.post("/api/analyze", json={"url": "https://example.com/"})
    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "req_full_001"
    assert body["data_quality"] == "full"
    assert set(body.keys()) == {
        "request_id",
        "url",
        "fetched_at",
        "data_quality",
        "summary",
        "issues",
        "rewrites",
        "limitations",
        "score",
    }


def test_analyze_rate_limits_per_ip(require_loop, monkeypatch):
    _mock_run_analysis(monkeypatch, _full_response())
    settings = Settings(
        frontend_origin="https://app.test", rate_limit_per_hour=3, log_level="WARNING"
    )
    limited = TestClient(create_app(settings))
    for _ in range(3):
        response = limited.post("/api/analyze", json={"url": "https://example.com/"})
        assert response.status_code == 200
    response = limited.post("/api/analyze", json={"url": "https://example.com/"})
    assert response.status_code == 429
    body = response.json()
    assert set(body.keys()) == ERROR_KEYS
    assert body["code"] == "RATE_LIMITED"
    assert body["retryable"] is True
    assert int(response.headers["Retry-After"]) >= 1


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("FETCH_BLOCKED", 502),
        ("NOT_HTML", 422),
        ("URL_BLOCKED", 400),
        ("FETCH_TIMEOUT", 504),
        ("UNSUPPORTED_SITE", 422),
    ],
)
def test_analyze_maps_fetch_errors(client, monkeypatch, code, status):
    _mock_run_analysis(monkeypatch, FetchError(code))
    response = client.post("/api/analyze", json={"url": "https://example.com/"})
    assert response.status_code == status
    body = response.json()
    assert set(body.keys()) == ERROR_KEYS
    assert body["code"] == code


def test_analyze_passes_through_custom_timeout_message(client, monkeypatch):
    _mock_run_analysis(monkeypatch, FetchError("FETCH_TIMEOUT", "Analysis timed out."))
    response = client.post("/api/analyze", json={"url": "https://example.com/"})
    assert response.status_code == 504
    assert response.json()["message"] == "Analysis timed out."


def test_cors_allows_only_configured_origin(client):
    allowed = client.get("/api/health", headers={"Origin": "https://app.test"})
    assert allowed.headers.get("access-control-allow-origin") == "https://app.test"
    denied = client.get("/api/health", headers={"Origin": "https://evil.test"})
    assert "access-control-allow-origin" not in denied.headers


def test_cors_preflight_allows_analyze_from_configured_origin(client):
    response = client.options(
        "/api/analyze",
        headers={
            "Origin": "https://app.test",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://app.test"


def test_app_exposes_expected_routes(app_settings):
    app = create_app(app_settings)
    by_path: dict[str, list[str]] = {}
    for route in app.routes:
        assert isinstance(route, Route)
        by_path[route.path] = sorted(route.methods or [])
    assert by_path == {
        "/api/account": ["DELETE"],
        "/api/analyze": ["POST"],
        "/api/contact": ["POST"],
        "/api/health": ["GET"],
        "/api/reports": ["GET"],
        "/api/reports/{report_id}": ["DELETE"],
    }
