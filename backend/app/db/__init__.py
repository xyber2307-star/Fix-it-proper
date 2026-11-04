"""Firestore access for Fix It Proper. Routes use repositories, never raw calls."""

from app.db.auth import AuthError, VerifiedUser, delete_auth_user, verify_id_token
from app.db.client import Database, build_database
from app.db.models import (
    ContactMessageDoc,
    DatabaseUnavailable,
    ProfileDoc,
    ReportDoc,
    UserDoc,
)
from app.db.repositories.contact_messages import ContactMessageRepository
from app.db.repositories.profiles import ProfileRepository
from app.db.repositories.reports import ReportRepository, normalize_report_url
from app.db.repositories.users import UserRepository

__all__ = [
    "AuthError",
    "ContactMessageDoc",
    "ContactMessageRepository",
    "Database",
    "DatabaseUnavailable",
    "ProfileDoc",
    "ProfileRepository",
    "ReportDoc",
    "ReportRepository",
    "UserDoc",
    "UserRepository",
    "VerifiedUser",
    "build_database",
    "delete_auth_user",
    "normalize_report_url",
    "verify_id_token",
]
