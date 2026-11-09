from sqlalchemy import CheckConstraint

from app.extensions import db
from .base import TimestampMixin, iso
from .constants import GENDERS, check_in

# Fields an applicant must fill in for the profile to count as complete.
# (The biography is optional.)
COMPLETION_FIELDS = (
    "first_name",
    "last_name",
    "phone",
    "date_of_birth",
    "gender",
    "nationality",
    "country_of_residence",
    "address",
    "passport_number",
    "passport_expiry",
    "position_applied",
    "years_experience",
)


class ApplicantProfile(TimestampMixin, db.Model):
    __tablename__ = "applicant_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30))
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(20))
    nationality = db.Column(db.String(100))
    country_of_residence = db.Column(db.String(100))
    address = db.Column(db.Text)
    passport_number = db.Column(db.String(20), unique=True)  # NULLs are allowed to repeat
    passport_expiry = db.Column(db.Date)
    position_applied = db.Column(db.String(100))
    years_experience = db.Column(db.Integer)
    biography = db.Column(db.Text)

    user = db.relationship("User", back_populates="profile")
    application = db.relationship(
        "Application", back_populates="applicant", uselist=False, cascade="all, delete-orphan"
    )
    documents = db.relationship(
        "Document",
        back_populates="applicant",
        cascade="all, delete-orphan",
        order_by="Document.created_at",
    )

    __table_args__ = (
        CheckConstraint(
            "gender IS NULL OR " + check_in("gender", GENDERS), name="gender_valid"
        ),
        CheckConstraint(
            "years_experience IS NULL OR (years_experience >= 0 AND years_experience <= 60)",
            name="experience_range",
        ),
        db.Index("ix_applicant_profiles_nationality", "nationality"),
        db.Index("ix_applicant_profiles_position_applied", "position_applied"),
        db.Index("ix_applicant_profiles_years_experience", "years_experience"),
        db.Index("ix_applicant_profiles_name", "last_name", "first_name"),
    )

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def missing_fields(self):
        return [f for f in COMPLETION_FIELDS if getattr(self, f) in (None, "")]

    @property
    def is_complete(self):
        return not self.missing_fields

    def to_dict(self):
        """Full profile (owner and admin views)."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "email": self.user.email if self.user else None,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "phone": self.phone,
            "date_of_birth": iso(self.date_of_birth),
            "gender": self.gender,
            "nationality": self.nationality,
            "country_of_residence": self.country_of_residence,
            "address": self.address,
            "passport_number": self.passport_number,
            "passport_expiry": iso(self.passport_expiry),
            "position_applied": self.position_applied,
            "years_experience": self.years_experience,
            "biography": self.biography,
            "is_complete": self.is_complete,
            "missing_fields": self.missing_fields,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }

    def to_summary(self):
        """Compact row for admin lists. Deliberately omits passport number, address and DOB."""
        app = self.application
        return {
            "id": self.id,
            "full_name": self.full_name,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.user.email if self.user else None,
            "phone": self.phone,
            "nationality": self.nationality,
            "position_applied": self.position_applied,
            "years_experience": self.years_experience,
            "is_complete": self.is_complete,
            "documents_count": len(self.documents),
            "application_id": app.id if app else None,
            "status": app.status if app else None,
            "created_at": iso(self.created_at),
        }
