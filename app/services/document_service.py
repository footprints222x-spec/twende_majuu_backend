from flask import current_app

from app.errors import APIError, Conflict, ValidationError
from app.extensions import db
from app.models import Document
from app.models.constants import DOCUMENT_RULES, DOCUMENT_TYPES
from app.services import storage_service
from app.utils import uploads


def _best_effort_delete(public_id, resource_type):
    """Remove an asset from storage; log (never raise) if it fails."""
    try:
        storage_service.delete_file(public_id, resource_type)
    except APIError as exc:
        current_app.logger.warning("Orphaned storage asset %s: %s", public_id, exc.message)


def upload_document(profile, file_storage, document_type):
    if document_type not in DOCUMENT_TYPES:
        raise ValidationError({"document_type": f"Must be one of: {', '.join(DOCUMENT_TYPES)}."})
    rules = DOCUMENT_RULES[document_type]

    upload = uploads.validate_upload(file_storage, document_type)

    existing = list(profile.documents)
    replaced = [d for d in existing if rules["single"] and d.document_type == document_type]
    remaining = len(existing) - len(replaced)
    if remaining >= current_app.config["MAX_DOCUMENTS_PER_APPLICANT"]:
        raise Conflict("Document limit reached. Delete an existing document before uploading another.")

    stored = storage_service.upload_private(
        upload.data,
        folder=f"applicants/{profile.id}",
        extension=upload.extension,
        resource_type=upload.resource_type,
    )

    old_assets = [(d.storage_public_id, d.storage_resource_type) for d in replaced]
    try:
        for old in replaced:
            db.session.delete(old)
        doc = Document(
            applicant_id=profile.id,
            document_type=document_type,
            original_filename=upload.filename,
            content_type=upload.content_type,
            file_size=upload.size,
            storage_public_id=stored.public_id,
            storage_resource_type=stored.resource_type,
            storage_format=stored.format,
        )
        db.session.add(doc)
        db.session.commit()
    except Exception:
        db.session.rollback()
        _best_effort_delete(stored.public_id, stored.resource_type)  # don't leave an orphan
        raise

    for public_id, resource_type in old_assets:
        _best_effort_delete(public_id, resource_type)
    return doc


def delete_document(doc):
    public_id, resource_type = doc.storage_public_id, doc.storage_resource_type
    db.session.delete(doc)
    db.session.commit()
    _best_effort_delete(public_id, resource_type)


def delete_all_assets(assets):
    """Delete many (public_id, resource_type) pairs, e.g. when an applicant is removed."""
    for public_id, resource_type in assets:
        _best_effort_delete(public_id, resource_type)


def open_download(doc):
    """Return an upstream streaming response for a document (raises StorageError)."""
    return storage_service.fetch_stream(doc)
