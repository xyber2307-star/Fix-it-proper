"""Repository for the contact_messages collection."""

import asyncio

from google.cloud.firestore import Client
from google.cloud.firestore_v1.collection import CollectionReference

from app.db.models import ContactMessageDoc, DatabaseUnavailable


class ContactMessageRepository:
    """Store and remove contact form submissions. No query by IP exists."""

    COLLECTION = "contact_messages"

    def __init__(self, client: Client | None) -> None:
        self._client = client

    def _collection(self) -> CollectionReference:
        if self._client is None:
            raise DatabaseUnavailable("contact store is disabled")
        return self._client.collection(self.COLLECTION)

    def _write_client(self) -> Client:
        if self._client is None:
            raise DatabaseUnavailable("contact store is disabled")
        return self._client

    async def save(self, doc: ContactMessageDoc) -> str:
        """Store a message and return its document id."""
        ref = self._collection().document()
        await asyncio.to_thread(ref.set, doc.model_dump(mode="python"))
        return str(ref.id)

    async def list_by_email(self, email: str) -> list[tuple[str, ContactMessageDoc]]:
        """Return id plus document for every message from an address."""

        def _run() -> list[tuple[str, ContactMessageDoc]]:
            found = []
            query = self._collection().where("email", "==", email).stream()
            for snap in query:
                data = snap.to_dict()
                if data is not None:
                    found.append((str(snap.id), ContactMessageDoc.model_validate(data)))
            return found

        return await asyncio.to_thread(_run)

    async def delete_by_email(self, email: str) -> int:
        """Delete every message from an address. Returns the count removed."""
        collection = self._collection()
        client = self._write_client()

        def _run() -> int:
            matches = list(collection.where("email", "==", email).stream())
            for index in range(0, len(matches), 400):
                batch = client.batch()
                for snap in matches[index : index + 400]:
                    batch.delete(snap.reference)
                batch.commit()
            return len(matches)

        return await asyncio.to_thread(_run)
