"""Tests for auth, saved reports, autosave, and account deletion."""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db import AuthError, ContactMessageDoc, VerifiedUser
from app.main import create_app
from app.schemas import AnalyzeResponse
from tests.conftest import emulator_settings, offline_settings

FIXTURES = Path(__file__).parent / "fixtures"
GOOD_TOKEN = "good-token"


def _response(request_id: str) -> AnalyzeResponse:
    data: dict[str, Any] = json.loads((FIXTURES / "full_success.json").read_text(encoding="utf-8"))
    data["request_id"] = request_id
    return AnalyzeResponse.model_validate(data)


@pytest.fixture
def authed_client(monkeypatch, require_emulator, require_loop):
    async def fake_verify(app: Any, token: str) -> VerifiedUser:
        if token == GOOD_TOKEN:
            return VerifiedUser(uid="user-1", email="user-1@example.com")
        raise AuthError("bad token")

    monkeypatch.setattr("app.main.verify_id_token", fake_verify)
    return TestClient(create_app(emulator_settings()))


def _headers(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_protected_routes_need_auth(authed_client):
    assert authed_client.get("/api/reports").status_code == 401
    assert authed_client.get("/api/reports").json()["code"] == "UNAUTHORIZED"
    assert authed_client.get("/api/reports", headers=_headers("bad")).status_code == 401
    assert authed_client.delete("/api/reports/x").status_code == 401
    assert authed_client.delete("/api/account").status_code == 401


def test_reports_list_empty_and_creates_user(authed_client):
    response = authed_client.get("/api/reports", headers=_headers())
    assert response.status_code == 200
    assert response.json() == {"reports": []}

    async def _body():
        user = await authed_client.app.state.db.users.get("user-1")
        assert user is not None
        assert user.email == "user-1@example.com"
        await authed_client.app.state.db.users.delete("user-1")

    asyncio.run(_body())


def test_analyze_autosaves_for_signed_in_user(authed_client, monkeypatch):
    request_id = f"req-{uuid.uuid4().hex}"

    async def fake_run_analysis(raw_url: str, **kwargs: Any) -> AnalyzeResponse:
        return _response(request_id)

    monkeypatch.setattr("app.main.run_analysis", fake_run_analysis)
    response = authed_client.post(
        "/api/analyze", json={"url": "https://example.com/"}, headers=_headers()
    )
    assert response.status_code == 200
    listed = authed_client.get("/api/reports", headers=_headers())
    assert listed.status_code == 200
    reports = listed.json()["reports"]
    assert len(reports) == 1
    assert reports[0]["id"] == request_id
    assert reports[0]["url"] == "https://example.com/"
    assert reports[0]["data_quality"] == "full"
    assert reports[0]["issue_count"] == 2
    assert reports[0]["score_value"] == 78.5

    async def _body():
        await authed_client.app.state.db.reports.delete(request_id)
        await authed_client.app.state.db.users.delete("user-1")

    asyncio.run(_body())


def test_analyze_invalid_token_saves_nothing(authed_client, monkeypatch):
    async def fake_run_analysis(raw_url: str, **kwargs: Any) -> AnalyzeResponse:
        return _response(f"req-{uuid.uuid4().hex}")

    monkeypatch.setattr("app.main.run_analysis", fake_run_analysis)
    response = authed_client.post(
        "/api/analyze", json={"url": "https://example.com/"}, headers=_headers("bad")
    )
    assert response.status_code == 200
    listed = authed_client.get("/api/reports", headers=_headers())
    assert listed.json() == {"reports": []}

    async def _body():
        await authed_client.app.state.db.users.delete("user-1")

    asyncio.run(_body())


def test_analyze_works_when_db_disabled(monkeypatch, require_loop):
    async def fake_verify(app: Any, token: str) -> VerifiedUser:
        raise AssertionError("must not verify when disabled")

    async def fake_run_analysis(raw_url: str, **kwargs: Any) -> AnalyzeResponse:
        return _response(f"req-{uuid.uuid4().hex}")

    monkeypatch.setattr("app.main.verify_id_token", fake_verify)
    monkeypatch.setattr("app.main.run_analysis", fake_run_analysis)
    offline = TestClient(create_app(offline_settings()))
    response = offline.post(
        "/api/analyze", json={"url": "https://example.com/"}, headers=_headers()
    )
    assert response.status_code == 200


def test_delete_report_owns_and_hides_foreign(authed_client):
    own_id = f"req-{uuid.uuid4().hex}"
    foreign_id = f"req-{uuid.uuid4().hex}"

    async def _seed():
        db = authed_client.app.state.db
        now = datetime.now(UTC)
        from app.db import ReportDoc

        await db.reports.save(
            ReportDoc(
                user_id="user-1",
                request_id=own_id,
                url="https://example.com/",
                data_quality="full",
                response={"summary": "mine"},
                created_at=now,
                expires_at=now,
            )
        )
        await db.reports.save(
            ReportDoc(
                user_id="user-2",
                request_id=foreign_id,
                url="https://example.com/",
                data_quality="full",
                response={"summary": "theirs"},
                created_at=now,
                expires_at=now,
            )
        )

    asyncio.run(_seed())
    assert authed_client.delete(f"/api/reports/{foreign_id}", headers=_headers()).status_code == 404
    assert authed_client.delete("/api/reports/missing", headers=_headers()).status_code == 404
    deleted = authed_client.delete(f"/api/reports/{own_id}", headers=_headers())
    assert deleted.status_code == 200
    assert deleted.json() == {"status": "deleted"}

    async def _cleanup():
        db = authed_client.app.state.db
        assert await db.reports.get(foreign_id) is not None
        await db.reports.delete(foreign_id)
        await db.users.delete("user-1")

    asyncio.run(_cleanup())


def test_delete_account_removes_everything(authed_client, monkeypatch):
    calls: list[str] = []

    async def fake_delete_auth(app: Any, uid: str) -> None:
        calls.append(uid)

    monkeypatch.setattr("app.main.delete_auth_user", fake_delete_auth)
    report_id = f"req-{uuid.uuid4().hex}"

    async def _seed():
        db = authed_client.app.state.db
        now = datetime.now(UTC)
        from app.db import ReportDoc

        await db.users.upsert("user-1", "user-1@example.com", now)
        await db.reports.save(
            ReportDoc(
                user_id="user-1",
                request_id=report_id,
                url="https://example.com/",
                data_quality="full",
                response={"summary": "mine"},
                created_at=now,
                expires_at=now,
            )
        )
        await db.contacts.save(
            ContactMessageDoc(
                name="User One",
                email="user-1@example.com",
                message="Please delete my message",
                created_at=now,
            )
        )

    asyncio.run(_seed())
    response = authed_client.delete("/api/account", headers=_headers())
    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}
    assert calls == ["user-1"]

    async def _verify():
        db = authed_client.app.state.db
        assert await db.users.get("user-1") is None
        assert await db.reports.get(report_id) is None
        assert await db.contacts.list_by_email("user-1@example.com") == []

    asyncio.run(_verify())


def test_protected_routes_503_when_db_disabled(monkeypatch, require_loop):
    async def fake_verify(app: Any, token: str) -> VerifiedUser:
        return VerifiedUser(uid="user-1", email="user-1@example.com")

    monkeypatch.setattr("app.main.verify_id_token", fake_verify)
    offline = TestClient(create_app(offline_settings()))
    response = offline.get("/api/reports", headers=_headers())
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
