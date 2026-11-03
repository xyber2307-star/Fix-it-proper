"""One repository module per Firestore collection."""

from app.db.repositories.contact_messages import ContactMessageRepository
from app.db.repositories.reports import ReportRepository
from app.db.repositories.users import UserRepository

__all__ = ["ContactMessageRepository", "ReportRepository", "UserRepository"]
