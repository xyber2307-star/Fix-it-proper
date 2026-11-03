"""Build the Firestore handle. Disabled, never crashing, when unconfigured."""

import base64
import binascii
import json
import logging
import os
from itertools import count
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore import Client

from app.brand import SLUG
from app.config import Settings
from app.db.repositories.contact_messages import ContactMessageRepository
from app.db.repositories.reports import ReportRepository
from app.db.repositories.users import UserRepository

logger = logging.getLogger(f"{SLUG}.db")

_app_counter = count()


class Database:
    """Owns the Firestore client and one repository per collection."""

    def __init__(self, app: firebase_admin.App | None, client: Client | None) -> None:
        self._app = app
        self._client = client
        self.contacts = ContactMessageRepository(client)
        self.users = UserRepository(client)
        self.reports = ReportRepository(client)

    @property
    def enabled(self) -> bool:
        """True when a usable Firestore client exists."""
        return self._client is not None

    @property
    def app(self) -> firebase_admin.App | None:
        """Firebase app handle for Auth calls. None when disabled."""
        return self._app


def _init_app(cred: credentials.Base | None, project_id: str) -> firebase_admin.App:
    name = f"{SLUG}-{next(_app_counter)}"
    if cred is None:
        return firebase_admin.initialize_app(options={"projectId": project_id}, name=name)
    return firebase_admin.initialize_app(cred, name=name)


def _certificate_from_base64(raw: str) -> credentials.Certificate | None:
    try:
        info: dict[str, Any] = json.loads(base64.b64decode(raw).decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("firebase credentials base64 is not valid JSON")
        return None
    return credentials.Certificate(info)


def build_database(settings: Settings) -> Database:
    """Create the database handle from settings.

    Emulator host wins when set. Otherwise a service account is needed,
    from base64 first, then file path. Anything missing or invalid
    yields a disabled Database instead of raising, so the API can
    still serve analysis without persistence.
    """
    if settings.firebase_auth_emulator_host.strip():
        os.environ["FIREBASE_AUTH_EMULATOR_HOST"] = settings.firebase_auth_emulator_host.strip()
    emulator = settings.firestore_emulator_host.strip()
    if emulator:
        os.environ["FIRESTORE_EMULATOR_HOST"] = emulator
        project = settings.firebase_project_id.strip() or "fix-it-proper-dev"
        app = _init_app(None, project)
        # The Admin SDK resolves real credentials before honoring the
        # emulator, so data access uses a direct client here. The Admin
        # SDK app is still used for Auth in both modes.
        return Database(app, Client(project=project))

    encoded = settings.firebase_credentials_base64.strip()
    if encoded:
        cert = _certificate_from_base64(encoded)
        if cert is None:
            return Database(None, None)
        app = _init_app(cert, settings.firebase_project_id.strip())
        return Database(app, firestore.client(app))

    path = settings.firebase_credentials_path.strip()
    if path:
        try:
            app = _init_app(credentials.Certificate(path), settings.firebase_project_id.strip())
        except (OSError, ValueError):
            logger.warning("firebase credentials file is missing or invalid")
            return Database(None, None)
        return Database(app, firestore.client(app))

    logger.info("firestore disabled: set emulator host or service account credentials")
    return Database(None, None)
