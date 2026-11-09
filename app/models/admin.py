from app.extensions import db
from .base import TimestampMixin, iso


class Admin(TimestampMixin, db.Model):
    """Administrator details, one-to-one with a User whose role is 'admin'."""

    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    full_name = db.Column(db.String(200), nullable=False)

    user = db.relationship("User", back_populates="admin")

    def to_dict(self):
        return {
            "id": self.id,
            "full_name": self.full_name,
            "created_at": iso(self.created_at),
        }
