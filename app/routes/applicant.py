from flask import Blueprint, Response, request, stream_with_context

from app.auth import current_user, role_required
from app.models.constants import ROLE_APPLICANT
from app.services import applicant_service, document_service
from app.utils.responses import json_body, success

applicant_bp = Blueprint("applicant", __name__)

applicant_only = role_required(ROLE_APPLICANT)


def stream_document(doc):
    """Stream a stored document to the client as a download.

    The file is fetched from private storage by the server on each request, so the
    client never receives a storage URL. Responses are marked non-cacheable.
    """
    upstream = document_service.open_download(doc)

    def generate():
        try:
            yield from upstream.iter_content(chunk_size=64 * 1024)
        finally:
            upstream.close()

    response = Response(stream_with_context(generate()), mimetype=doc.content_type)
    response.headers.set("Content-Disposition", "attachment", filename=doc.original_filename)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# ---- Profile -------------------------------------------------------------------
@applicant_bp.get("/profile")
@applicant_only
def get_profile():
    profile = applicant_service.get_profile_for_user(current_user())
    return success(profile.to_dict())


@applicant_bp.route("/profile", methods=["PUT", "PATCH"])
@applicant_only
def update_profile():
    """Partial update: send only the fields you want to change."""
    profile = applicant_service.get_profile_for_user(current_user())
    applicant_service.update_profile(profile, json_body())
    return success(profile.to_dict(), "Profile updated.")


# ---- Documents -------------------------------------------------------------------
@applicant_bp.get("/documents")
@applicant_only
def list_documents():
    profile = applicant_service.get_profile_for_user(current_user())
    return success({"items": [d.to_dict() for d in profile.documents]})


@applicant_bp.post("/documents")
@applicant_only
def upload_document():
    """multipart/form-data with fields `document_type` and `file`."""
    profile = applicant_service.get_profile_for_user(current_user())
    document_type = (request.form.get("document_type") or "").strip().lower()
    doc = document_service.upload_document(profile, request.files.get("file"), document_type)
    return success(doc.to_dict(), "Document uploaded.", 201)


@applicant_bp.get("/documents/<int:document_id>/download")
@applicant_only
def download_document(document_id):
    profile = applicant_service.get_profile_for_user(current_user())
    doc = applicant_service.get_owned_document(profile, document_id)
    return stream_document(doc)


@applicant_bp.delete("/documents/<int:document_id>")
@applicant_only
def delete_document(document_id):
    profile = applicant_service.get_profile_for_user(current_user())
    doc = applicant_service.get_owned_document(profile, document_id)
    document_service.delete_document(doc)
    return success(message="Document deleted.")


# ---- Application status ------------------------------------------------------------
@applicant_bp.get("/application")
@applicant_only
def get_application():
    profile = applicant_service.get_profile_for_user(current_user())
    return success(applicant_service.application_overview(profile))
