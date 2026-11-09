from sqlalchemy import CheckConstraint

from app.extensions import db
from .base import TimestampMixin, iso
from .constants import APPLICATION_STATUSES, STATUS_LABELS, STATUS_PENDING, check_in


class Application(TimestampMixin, db.Model):
    """One application per applicant; tracks the review status."""

    __tablename__ = "applications"

    id = db.Column(db.Integer, primary_key=True)
    applicant_id = db.Column(
        db.Integer,
        db.ForeignKey("applicant_profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    status = db.Column(db.String(20), nullable=False, default=STATUS_PENDING)
    admin_notes = db.Column(db.Text)  # internal; never shown to the applicant
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("admins.id", ondelete="SET NULL"))
    reviewed_at = db.Column(db.DateTime(timezone=True))

    applicant = db.relationship("ApplicantProfile", back_populates="application")
    reviewed_by = db.relationship("Admin")

    __table_args__ = (
        CheckConstraint(check_in("status", APPLICATION_STATUSES), name="status_valid"),
        db.Index("ix_applications_status", "status"),
    )

    def to_dict(self, include_notes=False):
        data = {
            "id": self.id,
            "applicant_id": self.applicant_id,
            "status": self.status,
            "status_label": STATUS_LABELS.get(self.status, self.status),
            "submitted_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
            "reviewed_at": iso(self.reviewed_at),
        }
        if include_notes:
            data["admin_notes"] = self.admin_notes
            data["reviewed_by"] = self.reviewed_by.full_name if self.reviewed_by else None
        return data
