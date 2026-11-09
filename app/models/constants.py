"""Shared enumerations and rules. Stored as plain strings + CHECK constraints
(portable and easy to migrate, unlike native database enums)."""

ROLE_APPLICANT = "applicant"
ROLE_ADMIN = "admin"
ROLES = (ROLE_APPLICANT, ROLE_ADMIN)

# ---- Application status -----------------------------------------------------
STATUS_PENDING = "pending"
STATUS_UNDER_REVIEW = "under_review"
STATUS_SHORTLISTED = "shortlisted"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

APPLICATION_STATUSES = (
    STATUS_PENDING,
    STATUS_UNDER_REVIEW,
    STATUS_SHORTLISTED,
    STATUS_APPROVED,
    STATUS_REJECTED,
)
STATUS_LABELS = {
    STATUS_PENDING: "Pending",
    STATUS_UNDER_REVIEW: "Under Review",
    STATUS_SHORTLISTED: "Shortlisted",
    STATUS_APPROVED: "Approved",
    STATUS_REJECTED: "Rejected",
}


def normalize_status(value):
    """'Under Review', 'under-review' and 'under_review' all map to 'under_review'."""
    if not isinstance(value, str):
        return None
    candidate = value.strip().lower().replace("-", "_").replace(" ", "_")
    return candidate if candidate in APPLICATION_STATUSES else None


# ---- Profile ------------------------------------------------------------------
GENDERS = ("male", "female", "other", "prefer_not_to_say")

SUGGESTED_POSITIONS = (
    "Captain",
    "Chef",
    "Deckhand",
    "Engineer",
    "Housekeeper",
    "Stewardess",
)

# ---- Documents ------------------------------------------------------------------
DOC_CV = "cv"
DOC_PASSPORT_PHOTO = "passport_photo"
DOC_PASSPORT_COPY = "passport_copy"
DOC_PROFESSIONAL_CERT = "professional_certificate"
DOC_MARITIME_CERT = "maritime_certificate"
DOC_OTHER = "other"

# "single": a new upload replaces the previous one of the same type.
DOCUMENT_RULES = {
    DOC_CV: {"label": "CV / Resume", "extensions": ("pdf", "docx"), "single": True},
    DOC_PASSPORT_PHOTO: {"label": "Passport photograph", "extensions": ("jpg", "jpeg", "png"), "single": True},
    DOC_PASSPORT_COPY: {"label": "Passport copy", "extensions": ("pdf", "jpg", "jpeg", "png"), "single": True},
    DOC_PROFESSIONAL_CERT: {"label": "Professional certificate", "extensions": ("pdf", "jpg", "jpeg", "png"), "single": False},
    DOC_MARITIME_CERT: {"label": "Maritime training certificate", "extensions": ("pdf", "jpg", "jpeg", "png"), "single": False},
    DOC_OTHER: {"label": "Other supporting document", "extensions": ("pdf", "docx", "jpg", "jpeg", "png"), "single": False},
}
DOCUMENT_TYPES = tuple(DOCUMENT_RULES)


def check_in(column, values):
    """Build the SQL for a CHECK (column IN (...)) constraint from trusted constants."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"
