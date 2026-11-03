"""Repository for the reports collection, scoped by owning user."""

import asyncio
from urllib.parse import urlsplit

from google.cloud.firestore import Client
from google.cloud.firestore_v1.collection import CollectionReference

from app.db.models import DatabaseUnavailable, ReportDoc

_DEFAULT_PORTS = {"http": 80, "https": 443}
_LIST_LIMIT = 50


def normalize_report_url(url: str) -> str:
    """Return a canonical URL string for storage. Pure, no network.

    Lowercases scheme and host, drops fragments, userinfo, and
    default ports, and keeps a single root slash for empty paths.
    Falls back to the trimmed input when parsing fails.
    """
    text = (url or "").strip()
    try:
        parts = urlsplit(text)
        scheme = parts.scheme.lower()
        host = (parts.hostname or "").lower().rstrip(".")
        if not scheme or not host:
            return text
        port = parts.port
        netloc = host if port is None or port == _DEFAULT_PORTS.get(scheme) else f"{host}:{port}"
        path = parts.path or "/"
        if len(path) > 1:
            path = path.rstrip("/") or "/"
        query = f"?{parts.query}" if parts.query else ""
        return f"{scheme}://{netloc}{path}{query}"
    except ValueError:
        return text


class ReportRepository:
    """Save, list, and delete per-user analysis reports."""

    COLLECTION = "reports"

    def __init__(self, client: Client | None) -> None:
        self._client = client

    def _collection(self) -> CollectionReference:
        if self._client is None:
            raise DatabaseUnavailable("report store is disabled")
        return self._client.collection(self.COLLECTION)

    def _write_client(self) -> Client:
        if self._client is None:
            raise DatabaseUnavailable("report store is disabled")
        return self._client

    async def save(self, doc: ReportDoc) -> str:
        """Store a report under its request_id and return that id."""
        ref = self._collection().document(doc.request_id)
        await asyncio.to_thread(ref.set, doc.model_dump(mode="python"))
        return str(ref.id)

    async def list_by_user(self, uid: str, limit: int = _LIST_LIMIT) -> list[ReportDoc]:
        """Return newest first reports owned by a user, oldest created first on ties."""

        def _run() -> list[ReportDoc]:
            query = (
                self._collection()
                .where("user_id", "==", uid)
                .order_by("created_at", direction="DESCENDING")
                .limit(max(limit, 1))
            )
            docs = []
            for snap in query.stream():
                data = snap.to_dict()
                if data is not None:
                    docs.append(ReportDoc.model_validate(data))
            return docs

        return await asyncio.to_thread(_run)

    async def get(self, report_id: str) -> ReportDoc | None:
        """Return one report, or None when missing."""

        def _run() -> ReportDoc | None:
            snap = self._collection().document(report_id).get()
            data = snap.to_dict()
            if not snap.exists or data is None:
                return None
            return ReportDoc.model_validate(data)

        return await asyncio.to_thread(_run)

    async def delete(self, report_id: str) -> None:
        """Delete one report. Missing reports are a no-op."""
        await asyncio.to_thread(self._collection().document(report_id).delete)

    async def delete_by_user(self, uid: str) -> int:
        """Delete every report owned by a user. Returns the count removed."""
        collection = self._collection()
        client = self._write_client()

        def _run() -> int:
            matches = list(collection.where("user_id", "==", uid).stream())
            for index in range(0, len(matches), 400):
                batch = client.batch()
                for snap in matches[index : index + 400]:
                    batch.delete(snap.reference)
                batch.commit()
            return len(matches)

        return await asyncio.to_thread(_run)
