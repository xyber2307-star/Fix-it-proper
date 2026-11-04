"""Pydantic models for Firestore documents. One model per collection."""

from datetime import datetime
from typing import Any, Literal

from app.schemas import BusinessProfile, DataQuality, StrictModel

ContactStatus = Literal["new", "read", "replied"]


class DatabaseUnavailable(Exception):
    """Raised when a repository is used while the database is disabled."""


class ContactMessageDoc(StrictModel):
    """A contact form submission. Never holds HTML, keys, or IP addresses."""

    name: str
    email: str
    message: str
    created_at: datetime
    status: ContactStatus = "new"


class UserDoc(StrictModel):
    """Account record keyed by Firebase Auth uid. Email comes from the ID token."""

    uid: str
    email: str
    created_at: datetime
    last_seen_at: datetime


class ProfileDoc(StrictModel):
    """Onboarding profile keyed by uid. Mirrors BusinessProfile plus updated_at."""

    uid: str
    profile: BusinessProfile
    updated_at: datetime


class ReportDoc(StrictModel):
    """A saved analysis. Response is the AnalyzeResponse JSON, never raw HTML."""

    user_id: str
    request_id: str
    url: str
    data_quality: DataQuality
    response: dict[str, Any]
    created_at: datetime
    expires_at: datetime
