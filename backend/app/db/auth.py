"""Firebase ID token verification for protected routes."""

import asyncio
import logging

import firebase_admin
from firebase_admin import auth as firebase_auth

from app.brand import SLUG
from app.schemas import StrictModel

logger = logging.getLogger(f"{SLUG}.auth")


class AuthError(Exception):
    """Raised when no usable verified user can be produced."""


class VerifiedUser(StrictModel):
    """Identity extracted from a verified Firebase ID token."""

    uid: str
    email: str | None = None


async def verify_id_token(app: firebase_admin.App, token: str) -> VerifiedUser:
    """Verify a Firebase ID token and return the embedded identity."""
    try:
        decoded = await asyncio.to_thread(firebase_auth.verify_id_token, token, app)
    except Exception as exc:
        raise AuthError("token verification failed") from exc
    uid = decoded.get("uid")
    if not isinstance(uid, str) or not uid:
        raise AuthError("token has no uid")
    email = decoded.get("email")
    return VerifiedUser(uid=uid, email=email if isinstance(email, str) else None)


async def delete_auth_user(app: firebase_admin.App, uid: str) -> None:
    """Delete a Firebase Auth user. Raises on failure so callers can retry."""
    await asyncio.to_thread(firebase_auth.delete_user, uid, app)
