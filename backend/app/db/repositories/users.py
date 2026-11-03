"""Repository for the users collection, keyed by Firebase Auth uid."""

import asyncio
from datetime import datetime

from google.cloud.firestore import Client
from google.cloud.firestore_v1.collection import CollectionReference

from app.db.models import DatabaseUnavailable, UserDoc


class UserRepository:
    """Create, read, and delete account records."""

    COLLECTION = "users"

    def __init__(self, client: Client | None) -> None:
        self._client = client

    def _collection(self) -> CollectionReference:
        if self._client is None:
            raise DatabaseUnavailable("user store is disabled")
        return self._client.collection(self.COLLECTION)

    async def upsert(self, uid: str, email: str, now: datetime) -> None:
        """Create the user on first sight, else refresh email and last seen."""

        def _run() -> None:
            ref = self._collection().document(uid)
            if ref.get().exists:
                ref.update({"email": email, "last_seen_at": now})
            else:
                doc = UserDoc(uid=uid, email=email, created_at=now, last_seen_at=now)
                ref.set(doc.model_dump(mode="python"))

        await asyncio.to_thread(_run)

    async def get(self, uid: str) -> UserDoc | None:
        """Return the user record, or None when missing."""

        def _run() -> UserDoc | None:
            snap = self._collection().document(uid).get()
            data = snap.to_dict()
            if not snap.exists or data is None:
                return None
            return UserDoc.model_validate(data)

        return await asyncio.to_thread(_run)

    async def delete(self, uid: str) -> None:
        """Delete the user record. Missing records are a no-op."""
        await asyncio.to_thread(self._collection().document(uid).delete)
