from sqlalchemy import CheckConstraint
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from .base import TimestampMixin, iso
from .constants import ROLES, ROLE_ADMIN, ROLE_APPLICANT, check_in


class User(TimestampMixin, db.Model):
    """A login account. Role is either 'applicant' or 'admin'."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True)  # stored lowercase
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default=ROLE_APPLICANT)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    last_login_at = db.Column(db.DateTime(timezone=True))

    profile = db.relationship(
        "ApplicantProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    admin = db.relationship("Admin", back_populates="user", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (CheckConstraint(check_in("role", ROLES), name="role_valid"),)

    @property
    def is_admin(self):
        return self.role == ROLE_ADMIN

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": iso(self.created_at),
            "last_login_at": iso(self.last_login_at),
        }

    def __repr__(self):
        return f"<User {self.id} {self.email} ({self.role})>"
