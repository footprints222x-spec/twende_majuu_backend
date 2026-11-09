from datetime import timezone, datetime

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


def iso(value):
    """ISO-8601 string for a datetime/date (naive datetimes are treated as UTC)."""
    if value is None:
        return None
    if isinstance(value, datetime) and value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)
