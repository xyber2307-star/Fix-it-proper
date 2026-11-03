"""Repository tests against the Firestore emulator. Never production."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from app.db import (
    ContactMessageDoc,
    ReportDoc,
    build_database,
)
from tests.conftest import emulator_settings

NOW = datetime(2026, 11, 3, 12, 0, 0, tzinfo=UTC)


def _uid() -> str:
    return f"test-{uuid.uuid4().hex}"


def test_contacts_save_list_and_delete(require_emulator, require_loop):
    email = f"{_uid()}@example.com"
    db = build_database(emulator_settings())

    async def _body():
        doc = ContactMessageDoc(
            name="Sam", email=email, message="Hello there friend", created_at=NOW
        )
        saved_id = await db.contacts.save(doc)
        assert saved_id
        found = await db.contacts.list_by_email(email)
        assert len(found) == 1
        assert found[0][0] == saved_id
        assert found[0][1].message == "Hello there friend"
        assert found[0][1].status == "new"
        assert await db.contacts.delete_by_email(email) == 1
        assert await db.contacts.list_by_email(email) == []
        assert await db.contacts.delete_by_email(email) == 0

    asyncio.run(_body())


def test_users_upsert_get_and_delete(require_emulator, require_loop):
    uid = _uid()
    db = build_database(emulator_settings())

    async def _body():
        assert await db.users.get(uid) is None
        await db.users.upsert(uid, "first@example.com", NOW)
        first = await db.users.get(uid)
        assert first is not None
        assert first.email == "first@example.com"
        assert first.created_at == NOW
        later = NOW + timedelta(hours=1)
        await db.users.upsert(uid, "second@example.com", later)
        second = await db.users.get(uid)
        assert second is not None
        assert second.email == "second@example.com"
        assert second.last_seen_at == later
        assert second.created_at == NOW
        await db.users.delete(uid)
        assert await db.users.get(uid) is None

    asyncio.run(_body())


def _report(uid: str, request_id: str, created: datetime) -> ReportDoc:
    return ReportDoc(
        user_id=uid,
        request_id=request_id,
        url="https://example.com/",
        data_quality="full",
        response={"summary": "ok", "issues": [], "rewrites": [], "limitations": []},
        created_at=created,
        expires_at=created + timedelta(days=30),
    )


def test_reports_save_get_and_expiry_is_timestamp(require_emulator, require_loop):
    uid = _uid()
    request_id = f"req-{_uid()}"
    db = build_database(emulator_settings())

    async def _body():
        assert await db.reports.get(request_id) is None
        await db.reports.save(_report(uid, request_id, NOW))
        fetched = await db.reports.get(request_id)
        assert fetched is not None
        assert fetched.user_id == uid
        assert isinstance(fetched.expires_at, datetime)
        assert fetched.expires_at == NOW + timedelta(days=30)
        await db.reports.delete(request_id)
        assert await db.reports.get(request_id) is None

    asyncio.run(_body())


def test_reports_list_is_scoped_and_newest_first(require_emulator, require_loop):
    mine, theirs = _uid(), _uid()
    first_id, second_id, foreign_id = f"req-{_uid()}", f"req-{_uid()}", f"req-{_uid()}"
    db = build_database(emulator_settings())

    async def _body():
        await db.reports.save(_report(mine, first_id, NOW))
        await db.reports.save(_report(mine, second_id, NOW + timedelta(minutes=1)))
        await db.reports.save(_report(theirs, foreign_id, NOW + timedelta(minutes=2)))
        mine_only = await db.reports.list_by_user(mine)
        assert [doc.request_id for doc in mine_only] == [second_id, first_id]
        assert await db.reports.delete_by_user(mine) == 2
        assert await db.reports.list_by_user(mine) == []
        assert await db.reports.get(foreign_id) is not None
        assert await db.reports.delete_by_user(theirs) == 1

    asyncio.run(_body())
