"""Tests for Firestore document models, URL normalization, and db setup."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.db import (
    ContactMessageDoc,
    ReportDoc,
    UserDoc,
    build_database,
    normalize_report_url,
)
from app.db.models import DatabaseUnavailable
from tests.conftest import offline_settings

NOW = datetime(2026, 11, 3, 12, 0, 0, tzinfo=UTC)


def test_contact_message_defaults_to_new_and_forbids_extra():
    doc = ContactMessageDoc(
        name="Sam", email="sam@example.com", message="Hello there friend", created_at=NOW
    )
    assert doc.status == "new"
    with pytest.raises(ValidationError):
        ContactMessageDoc(
            name="Sam",
            email="sam@example.com",
            message="Hello there friend",
            created_at=NOW,
            ip="1.2.3.4",
        )


def test_user_and_report_roundtrip():
    user = UserDoc.model_validate(
        {"uid": "u1", "email": "u1@example.com", "created_at": NOW, "last_seen_at": NOW}
    )
    assert user.uid == "u1"
    report = ReportDoc.model_validate(
        {
            "user_id": "u1",
            "request_id": "req-1",
            "url": "https://example.com/",
            "data_quality": "full",
            "response": {"summary": "ok"},
            "created_at": NOW,
            "expires_at": NOW + timedelta(days=30),
        }
    )
    assert report.expires_at > report.created_at


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://Example.COM/page", "https://example.com/page"),
        ("https://example.com:443/", "https://example.com/"),
        ("http://example.com:80/a/", "http://example.com/a"),
        ("https://example.com/a#frag", "https://example.com/a"),
        ("https://example.com/a?b=1", "https://example.com/a?b=1"),
        ("https://example.com", "https://example.com/"),
        ("not a url", "not a url"),
        ("", ""),
    ],
)
def test_normalize_report_url(raw, expected):
    assert normalize_report_url(raw) == expected


def test_build_database_disabled_when_unconfigured():
    db = build_database(offline_settings())
    assert db.enabled is False
    assert db.app is None


def test_build_database_disabled_on_bad_base64():
    settings = offline_settings(firebase_credentials_base64="!!!not-base64!!!")
    assert build_database(settings).enabled is False


def test_build_database_disabled_on_missing_file():
    settings = offline_settings(firebase_credentials_path="C:/does/not/exist.json")
    assert build_database(settings).enabled is False


def test_repositories_raise_when_disabled():
    import asyncio

    from tests.conftest import skip_without_loop

    skip_without_loop()
    db = build_database(offline_settings())
    doc = ContactMessageDoc(
        name="Sam", email="sam@example.com", message="Hello there friend", created_at=NOW
    )
    with pytest.raises(DatabaseUnavailable):
        asyncio.run(db.contacts.save(doc))


def test_build_database_emulator_enables_without_network():
    old = os.environ.get("FIRESTORE_EMULATOR_HOST")
    try:
        settings = Settings(
            firestore_emulator_host="127.0.0.1:9",
            firebase_project_id="fix-it-proper-test",
            log_level="WARNING",
        )
        assert build_database(settings).enabled is True
    finally:
        if old is None:
            os.environ.pop("FIRESTORE_EMULATOR_HOST", None)
        else:
            os.environ["FIRESTORE_EMULATOR_HOST"] = old
