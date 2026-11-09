from flask import Blueprint, current_app, request

from app.auth import current_user, role_required
from app.models.constants import ROLE_ADMIN
from app.routes.applicant import stream_document
from app.services import admin_service
from app.utils.responses import json_body, success

admin_bp = Blueprint("admin", __name__)

admin_only = role_required(ROLE_ADMIN)


def _audit(action, **details):
    """Audit trail for sensitive admin actions (goes to the application log)."""
    current_app.logger.info(
        "ADMIN_AUDIT admin_user_id=%s action=%s %s",
        current_user().id,
        action,
        " ".join(f"{k}={v}" for k, v in details.items()),
    )


@admin_bp.get("/applicants")
@admin_only
def list_applicants():
    return success(admin_service.list_applicants(request.args))


@admin_bp.get("/applicants/<int:applicant_id>")
@admin_only
def get_applicant(applicant_id):
    profile = admin_service.get_applicant(applicant_id)
    _audit("view_applicant", applicant_id=applicant_id)
    return success(admin_service.applicant_detail(profile))


@admin_bp.delete("/applicants/<int:applicant_id>")
@admin_only
def delete_applicant(applicant_id):
    profile = admin_service.get_applicant(applicant_id)
    removed = admin_service.delete_applicant(profile)
    _audit("delete_applicant", applicant_id=applicant_id, files_removed=removed)
    return success(message="Applicant and all associated documents deleted.")


@admin_bp.get("/documents/<int:document_id>/download")
@admin_only
def download_document(document_id):
    doc = admin_service.get_document(document_id)
    _audit("download_document", document_id=document_id, applicant_id=doc.applicant_id, type=doc.document_type)
    return stream_document(doc)


@admin_bp.route("/applications/<int:application_id>/status", methods=["PUT", "PATCH"])
@admin_only
def update_status(application_id):
    """{"status": "pending|under_review|shortlisted|approved|rejected", "admin_notes": "optional"}"""
    application, previous = admin_service.update_status(
        application_id, json_body(), current_user().admin
    )
    _audit("update_status", application_id=application_id, old=previous, new=application.status)
    return success(application.to_dict(include_notes=True), "Application status updated.")


@admin_bp.get("/dashboard/stats")
@admin_only
def dashboard_stats():
    return success(admin_service.dashboard_stats())
