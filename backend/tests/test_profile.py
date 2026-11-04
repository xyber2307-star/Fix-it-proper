"""Tests for business profile validation and storage."""

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.db import AuthError, VerifiedUser
from app.main import create_app
from app.schemas import BusinessProfile
from tests.conftest import emulator_settings

GOOD_TOKEN = "good-token"


def _profile(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "business_name": "Springfield Plumbing",
        "website": "https://springfield-plumbing.example.com",
        "industry": "Home services",
        "city": "Springfield",
        "country": "United States",
        "size": "2 to 10",
        "role": "Owner",
    }
    values.update(overrides)
    return values


def test_profile_requires_all_business_fields():
    for field in ("business_name", "website", "industry", "city", "country", "size", "role"):
        values = _profile()
        del values[field]
        with pytest.raises(ValidationError):
            BusinessProfile.model_validate(values)


def test_profile_optional_fields_default_empty():
    profile = BusinessProfile.model_validate(_profile())
    assert profile.usage_plan == ""
    assert profile.profession == ""
    assert profile.referral_source == ""
    assert profile.help_feedback == ""


def test_profile_rejects_bad_size():
    with pytest.raises(ValidationError):
        BusinessProfile.model_validate(_profile(size="huge"))


def test_profile_website_gets_https_scheme():
    profile = BusinessProfile.model_validate(_profile(website="example.com/shop"))
    assert profile.website == "https://example.com/shop"


def test_profile_website_rejects_non_http():
    with pytest.raises(ValidationError):
        BusinessProfile.model_validate(_profile(website="ftp://example.com"))


def test_profile_website_rejects_bare_word():
    with pytest.raises(ValidationError):
        BusinessProfile.model_validate(_profile(website="not a site"))


def test_profile_rejects_extra_fields():
    with pytest.raises(ValidationError):
        BusinessProfile.model_validate(_profile(nickname="x"))


@pytest.fixture
def authed_client(monkeypatch, require_emulator, require_loop):
    async def fake_verify(app: Any, token: str) -> VerifiedUser:
        if token == GOOD_TOKEN:
            return VerifiedUser(uid="profile-user-1", email="profile-user-1@example.com")
        raise AuthError("bad token")

    monkeypatch.setattr("app.main.verify_id_token", fake_verify)
    return TestClient(create_app(emulator_settings()))


def _headers(token: str = GOOD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_profile_endpoints_need_auth(authed_client):
    assert authed_client.get("/api/profile").status_code == 401
    assert authed_client.put("/api/profile", json=_profile()).status_code == 401
    assert authed_client.get("/api/profile", headers=_headers("bad")).status_code == 401


def test_profile_roundtrip(authed_client):
    first = authed_client.get("/api/profile", headers=_headers())
    assert first.status_code == 200
    assert first.json() == {"profile": None, "profile_complete": False}

    payload = _profile(usage_plan="Check my homepage monthly.", profession="Plumber")
    saved = authed_client.put("/api/profile", json=payload, headers=_headers())
    assert saved.status_code == 200
    body = saved.json()
    assert body["profile_complete"] is True
    assert body["profile"]["business_name"] == "Springfield Plumbing"
    assert body["profile"]["profession"] == "Plumber"

    again = authed_client.get("/api/profile", headers=_headers())
    assert again.json()["profile"]["website"] == "https://springfield-plumbing.example.com"

    async def _cleanup() -> None:
        await authed_client.app.state.db.profiles.delete("profile-user-1")
        await authed_client.app.state.db.users.delete("profile-user-1")

    asyncio.run(_cleanup())


def test_profile_put_rejects_invalid(authed_client):
    bad = _profile(business_name="X")
    response = authed_client.put("/api/profile", json=bad, headers=_headers())
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"


def test_profile_put_strips_markup(authed_client):
    payload = _profile(business_name="<b>Springfield Plumbing</b>")
    saved = authed_client.put("/api/profile", json=payload, headers=_headers())
    assert saved.status_code == 200
    assert saved.json()["profile"]["business_name"] == "Springfield Plumbing"

    async def _cleanup() -> None:
        await authed_client.app.state.db.profiles.delete("profile-user-1")
        await authed_client.app.state.db.users.delete("profile-user-1")

    asyncio.run(_cleanup())
