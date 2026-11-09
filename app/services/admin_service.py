from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import selectinload

from app.errors import NotFound, ValidationError
from app.extensions import db
from app.models import ApplicantProfile, Application, Document, User
from app.models.applicant_profile import COMPLETION_FIELDS
from app.models.constants import (
    APPLICATION_STATUSES,
    DOC_CV,
    STATUS_LABELS,
    normalize_status,
)
from app.services import document_service
from app.utils import validators as v

SORTABLE = {
    "created_at": ApplicantProfile.created_at,
    "last_name": ApplicantProfile.last_name,
    "first_name": ApplicantProfile.first_name,
    "years_experience": ApplicantProfile.years_experience,
    "status": Application.status,
}


def _int_param(args, name, default=None, minimum=0, maximum=None):
    raw = args.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationError({name: "Must be a whole number."})
    if value < minimum or (maximum is not None and value > maximum):
        bound = f"between {minimum} and {maximum}" if maximum is not None else f"at least {minimum}"
        raise ValidationError({name: f"Must be {bound}."})
    return value


def list_applicants(args):
    """Paginated, searchable, filterable applicant list.

    Query params: q, nationality, position, status, min_experience, max_experience,
    sort_by, order (asc|desc), page, per_page (max 100).
    """
    page = _int_param(args, "page", 1, minimum=1)
    per_page = _int_param(args, "per_page", 20, minimum=1, maximum=100)
    min_exp = _int_param(args, "min_experience")
    max_exp = _int_param(args, "max_experience")

    stmt = (
        db.select(ApplicantProfile)
        .join(User, ApplicantProfile.user_id == User.id)
        .join(Application, Application.applicant_id == ApplicantProfile.id)
        .options(
            selectinload(ApplicantProfile.user),
            selectinload(ApplicantProfile.application),
            selectinload(ApplicantProfile.documents),
        )
    )

    q = (args.get("q") or "").strip()
    for term in q.split()[:6]:  # every word must match name, email or position
        like = f"%{v.escape_like(term.lower())}%"
        stmt = stmt.where(
            or_(
                func.lower(ApplicantProfile.first_name).like(like, escape="\\"),
                func.lower(ApplicantProfile.last_name).like(like, escape="\\"),
                func.lower(User.email).like(like, escape="\\"),
                func.lower(ApplicantProfile.position_applied).like(like, escape="\\"),
            )
        )

    nationality = (args.get("nationality") or "").strip()
    if nationality:
        like = f"%{v.escape_like(nationality.lower())}%"
        stmt = stmt.where(func.lower(ApplicantProfile.nationality).like(like, escape="\\"))

    position = (args.get("position") or "").strip()
    if position:
        like = f"%{v.escape_like(position.lower())}%"
        stmt = stmt.where(func.lower(ApplicantProfile.position_applied).like(like, escape="\\"))

    status_raw = args.get("status")
    if status_raw:
        status = normalize_status(status_raw)
        if status is None:
            raise ValidationError({"status": f"Must be one of: {', '.join(APPLICATION_STATUSES)}."})
        stmt = stmt.where(Application.status == status)

    if min_exp is not None:
        stmt = stmt.where(ApplicantProfile.years_experience >= min_exp)
    if max_exp is not None:
        stmt = stmt.where(ApplicantProfile.years_experience <= max_exp)

    sort_by = args.get("sort_by", "created_at")
    if sort_by not in SORTABLE:
        raise ValidationError({"sort_by": f"Must be one of: {', '.join(SORTABLE)}."})
    order = args.get("order", "desc").lower()
    if order not in ("asc", "desc"):
        raise ValidationError({"order": "Must be 'asc' or 'desc'."})
    column = SORTABLE[sort_by]
    stmt = stmt.order_by(column.asc() if order == "asc" else column.desc(), ApplicantProfile.id.desc())

    pagination = db.paginate(stmt, page=page, per_page=per_page, error_out=False)
    return {
        "items": [p.to_summary() for p in pagination.items],
        "pagination": {
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
            "pages": pagination.pages,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev,
        },
    }


def get_applicant(applicant_id):
    profile = db.session.get(ApplicantProfile, applicant_id)
    if profile is None:
        raise NotFound("Applicant not found.")
    return profile


def applicant_detail(profile):
    data = profile.to_dict()
    data["is_active"] = profile.user.is_active
    data["application"] = profile.application.to_dict(include_notes=True)
    data["documents"] = [d.to_dict() for d in profile.documents]
    return data


def get_document(document_id):
    doc = db.session.get(Document, document_id)
    if doc is None:
        raise NotFound("Document not found.")
    return doc


def update_status(application_id, data, admin):
    application = db.session.get(Application, application_id)
    if application is None:
        raise NotFound("Application not found.")

    status = normalize_status(data.get("status"))
    if status is None:
        raise ValidationError(
            {"status": f"Must be one of: {', '.join(APPLICATION_STATUSES)}."}
        )
    notes = data.get("admin_notes", "__unset__")
    if notes != "__unset__":
        if notes is not None and not isinstance(notes, str):
            raise ValidationError({"admin_notes": "Must be text."})
        if isinstance(notes, str) and len(notes) > 2000:
            raise ValidationError({"admin_notes": "Must be at most 2000 characters."})

    previous = application.status
    application.status = status
    if notes != "__unset__":
        application.admin_notes = (notes or "").strip() or None
    application.reviewed_by_id = admin.id
    application.reviewed_at = datetime.now(timezone.utc)
    db.session.commit()
    return application, previous


def delete_applicant(profile):
    """Remove the applicant's account, profile, application and stored files."""
    assets = [(d.storage_public_id, d.storage_resource_type) for d in profile.documents]
    db.session.delete(profile.user)  # cascades to profile, application, documents
    db.session.commit()
    document_service.delete_all_assets(assets)
    return len(assets)


def _top(column, limit=10):
    rows = (
        db.session.query(column, func.count(ApplicantProfile.id))
        .filter(column.isnot(None))
        .group_by(column)
        .order_by(func.count(ApplicantProfile.id).desc(), column)
        .limit(limit)
        .all()
    )
    return [{"name": name, "count": count} for name, count in rows]


def dashboard_stats():
    now = datetime.now(timezone.utc)
    total = db.session.query(func.count(ApplicantProfile.id)).scalar()

    by_status = {s: 0 for s in APPLICATION_STATUSES}
    for status, count in db.session.query(Application.status, func.count(Application.id)).group_by(
        Application.status
    ):
        by_status[status] = count

    def registered_since(delta):
        return (
            db.session.query(func.count(ApplicantProfile.id))
            .filter(ApplicantProfile.created_at >= now - delta)
            .scalar()
        )

    complete_clause = and_(
        *[
            getattr(ApplicantProfile, f).isnot(None)
            for f in COMPLETION_FIELDS
        ]
    )
    complete = db.session.query(func.count(ApplicantProfile.id)).filter(complete_clause).scalar()
    with_cv = (
        db.session.query(func.count(func.distinct(Document.applicant_id)))
        .filter(Document.document_type == DOC_CV)
        .scalar()
    )
    avg_exp = db.session.query(func.avg(ApplicantProfile.years_experience)).scalar()

    return {
        "total_applicants": total,
        "registrations": {
            "last_24_hours": registered_since(timedelta(days=1)),
            "last_7_days": registered_since(timedelta(days=7)),
            "last_30_days": registered_since(timedelta(days=30)),
        },
        "by_status": [
            {"status": s, "label": STATUS_LABELS[s], "count": by_status[s]} for s in APPLICATION_STATUSES
        ],
        "top_positions": _top(ApplicantProfile.position_applied),
        "top_nationalities": _top(ApplicantProfile.nationality),
        "profiles_complete": complete,
        "applicants_with_cv": with_cv,
        "average_years_experience": round(float(avg_exp), 1) if avg_exp is not None else None,
    }
