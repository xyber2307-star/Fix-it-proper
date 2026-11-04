"""Repository for the profiles collection, keyed by Firebase Auth uid."""

import asyncio
from datetime import datetime

from google.cloud.firestore import Client
from google.cloud.firestore_v1.collection import CollectionReference

from app.db.models import DatabaseUnavailable, ProfileDoc
from app.schemas import BusinessProfile


class ProfileRepository:
    """Save and read one onboarding profile per user."""

    COLLECTION = "profiles"

    def __init__(self, client: Client | None) -> None:
        self._client = client

    def _collection(self) -> CollectionReference:
        if self._client is None:
            raise DatabaseUnavailable("profile store is disabled")
        return self._client.collection(self.COLLECTION)

    async def save(self, uid: str, profile: BusinessProfile, now: datetime) -> None:
        """Replace the user's profile. The schema already validated every field."""

        def _run() -> None:
            doc = ProfileDoc(uid=uid, profile=profile, updated_at=now)
            self._collection().document(uid).set(doc.model_dump(mode="python"))

        await asyncio.to_thread(_run)

    async def get(self, uid: str) -> ProfileDoc | None:
        """Return the profile record, or None when the user skipped onboarding."""

        def _run() -> ProfileDoc | None:
            snap = self._collection().document(uid).get()
            data = snap.to_dict()
            if not snap.exists or data is None:
                return None
            return ProfileDoc.model_validate(data)

        return await asyncio.to_thread(_run)

    async def delete(self, uid: str) -> None:
        """Delete the profile record. Missing records are a no-op."""
        await asyncio.to_thread(self._collection().document(uid).delete)
