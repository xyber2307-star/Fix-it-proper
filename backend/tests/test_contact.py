"""Tests for POST /api/contact: validation, honeypot, storage, limits."""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import emulator_settings, offline_settings

ERROR_KEYS = {"code", "message", "retryable"}


@pytest.fixture
def client(require_emulator, require_loop):
    return TestClient(create_app(emulator_settings()))


def _email() -> str:
    return f"contact-{uuid.uuid4().hex}@example.com"


def test_contact_validation_errors_use_contract_shape(client):
    bad_email = client.post(
        "/api/contact",
        json={"name": "Sam Rivera", "email": "bad-email", "message": "Long enough message"},
    )
    assert bad_email.status_code == 422
    assert set(bad_email.json()) == ERROR_KEYS
    assert bad_email.json()["code"] == "INVALID_REQUEST"
    short = client.post(
        "/api/contact", json={"name": "S", "email": "s@example.com", "message": "short"}
    )
    assert short.status_code == 422
    assert short.json()["code"] == "INVALID_REQUEST"


def test_contact_honeypot_succeeds_without_storing(client):
    email = _email()
    response = client.post(
        "/api/contact",
        json={
            "name": "Bot",
            "email": email,
            "message": "Spam message here now",
            "company": "bot corp",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"status": "received"}

    async def _body():
        assert await client.app.state.db.contacts.list_by_email(email) == []

    asyncio.run(_body())


def test_contact_stores_sanitized_message(client):
    email = _email()
    response = client.post(
        "/api/contact",
        json={
            "name": "  Sam   Rivera  ",
            "email": email,
            "message": "Hello <b>there</b> friend, this stays long enough.",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"status": "received"}

    async def _body():
        found = await client.app.state.db.contacts.list_by_email(email)
        assert len(found) == 1
        assert found[0][1].name == "Sam Rivera"
        assert "<" not in found[0][1].message
        assert "  " not in found[0][1].message
        assert await client.app.state.db.contacts.delete_by_email(email) == 1

    asyncio.run(_body())


def test_contact_markup_only_message_rejected(client):
    response = client.post(
        "/api/contact",
        json={"name": "Sam Rivera", "email": _email(), "message": "<div>  hi  </div>!!"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


def test_contact_rate_limit_uses_contact_message(require_emulator, require_loop):
    limited = TestClient(create_app(emulator_settings(contact_rate_limit_per_hour=2)))
    payload = {"name": "Sam Rivera", "email": _email(), "message": "Long enough message here"}
    assert limited.post("/api/contact", json=payload).status_code == 200
    assert limited.post("/api/contact", json=payload).status_code == 200
    blocked = limited.post("/api/contact", json=payload)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "RATE_LIMITED"
    assert "messages" in blocked.json()["message"]
    assert blocked.headers["Retry-After"]

    async def _body():
        await limited.app.state.db.contacts.delete_by_email(payload["email"])

    asyncio.run(_body())


def test_contact_db_disabled_returns_503(require_loop):
    offline = TestClient(create_app(offline_settings()))
    response = offline.post(
        "/api/contact",
        json={"name": "Sam Rivera", "email": "sam@example.com", "message": "Long enough"},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert response.json()["retryable"] is True
