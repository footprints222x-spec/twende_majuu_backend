from flask import Blueprint
from sqlalchemy import text

from app.errors import error_response
from app.extensions import db
from app.models.constants import (
    APPLICATION_STATUSES,
    DOCUMENT_RULES,
    GENDERS,
    STATUS_LABELS,
    SUGGESTED_POSITIONS,
)
from app.utils.responses import success

meta_bp = Blueprint("meta", __name__)


@meta_bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        return error_response(503, "database_unavailable", "Database is unreachable.")
    return success({"status": "ok"})


@meta_bp.get("/options")
def options():
    """Static option lists so the React forms don't hard-code them."""
    return success(
        {
            "genders": list(GENDERS),
            "suggested_positions": list(SUGGESTED_POSITIONS),
            "application_statuses": [
                {"value": s, "label": STATUS_LABELS[s]} for s in APPLICATION_STATUSES
            ],
            "document_types": [
                {
                    "value": key,
                    "label": rule["label"],
                    "allowed_extensions": list(rule["extensions"]),
                    "replaces_previous": rule["single"],
                }
                for key, rule in DOCUMENT_RULES.items()
            ],
        }
    )
