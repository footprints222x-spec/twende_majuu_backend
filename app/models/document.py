from sqlalchemy import CheckConstraint

from app.extensions import db
from .base import iso, utcnow
from .constants import DOCUMENT_RULES, DOCUMENT_TYPES, check_in


class Document(db.Model):
    """Metadata for one uploaded file.

    The file itself lives in Cloudinary as an *authenticated* (private) asset.
    No delivery URL is stored or returned: files are only reachable through
    the authorised download endpoints, which stream them from storage.
    """

    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    applicant_id = db.Column(
        db.Integer, db.ForeignKey("applicant_profiles.id", ondelete="CASCADE"), nullable=False
    )
    document_type = db.Column(db.String(30), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(100), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)

    storage_public_id = db.Column(db.String(255), nullable=False, unique=True)
    storage_resource_type = db.Column(db.String(10), nullable=False)  # 'image' | 'raw'
    storage_format = db.Column(db.String(10))  # extension reported by Cloudinary (images)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    applicant = db.relationship("ApplicantProfile", back_populates="documents")

    __table_args__ = (
        CheckConstraint(check_in("document_type", DOCUMENT_TYPES), name="type_valid"),
        db.Index("ix_documents_applicant_id_type", "applicant_id", "document_type"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "document_type": self.document_type,
            "document_type_label": DOCUMENT_RULES[self.document_type]["label"],
            "original_filename": self.original_filename,
            "content_type": self.content_type,
            "file_size": self.file_size,
            "uploaded_at": iso(self.created_at),
        }
