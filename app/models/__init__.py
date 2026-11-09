"""Import every model here so Flask-Migrate / SQLAlchemy can see them."""
from .admin import Admin
from .applicant_profile import ApplicantProfile
from .application import Application
from .document import Document
from .token_blocklist import TokenBlocklist
from .user import User

__all__ = ["Admin", "ApplicantProfile", "Application", "Document", "TokenBlocklist", "User"]
