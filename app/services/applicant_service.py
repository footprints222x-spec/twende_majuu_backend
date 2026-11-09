from sqlalchemy.exc import IntegrityError

from app.errors import Conflict, NotFound
from app.extensions import db
from app.models import ApplicantProfile, Document
from app.models.constants import DOC_CV, DOC_PASSPORT_COPY, DOC_PASSPORT_PHOTO
from app.utils import validators as v


def get_profile_for_user(user):
    profile = user.profile
    if profile is None:
        raise NotFound("No applicant profile exists for this account.")
    return profile


def ensure_passport_unique(passport_number, exclude_profile_id=None):
    if not passport_number:
        return
    query = ApplicantProfile.query.filter_by(passport_number=passport_number)
    if exclude_profile_id is not None:
        query = query.filter(ApplicantProfile.id != exclude_profile_id)
    if query.first():
        raise Conflict(
            "This passport number is already registered.",
            details={"passport_number": "Already registered."},
        )


def update_profile(profile, data):
    """Apply a partial update. Only whitelisted profile fields are touched."""
    cleaned = v.validate_profile(data, creating=False)
    if "passport_number" in cleaned:
        ensure_passport_unique(cleaned["passport_number"], exclude_profile_id=profile.id)
    for field, value in cleaned.items():
        setattr(profile, field, value)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise Conflict("This passport number is already registered.")
    return profile


def application_overview(profile):
    """What the applicant sees on their status page: status + a document checklist."""
    present = {d.document_type for d in profile.documents}
    return {
        "application": profile.application.to_dict(include_notes=False),
        "profile_complete": profile.is_complete,
        "missing_profile_fields": profile.missing_fields,
        "checklist": {
            "cv": DOC_CV in present,
            "passport_photo": DOC_PASSPORT_PHOTO in present,
            "passport_copy": DOC_PASSPORT_COPY in present,
        },
        "documents_count": len(profile.documents),
    }


def get_owned_document(profile, document_id):
    doc = db.session.get(Document, document_id)
    # 404 (not 403) for someone else's document so IDs cannot be probed.
    if doc is None or doc.applicant_id != profile.id:
        raise NotFound("Document not found.")
    return doc
