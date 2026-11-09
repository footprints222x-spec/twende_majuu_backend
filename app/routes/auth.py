from flask import Blueprint, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required, verify_jwt_in_request

from app.auth import current_user, role_required
from app.errors import Unauthorized
from app.extensions import db
from app.models import User
from app.services import auth_service
from app.utils.responses import json_body, success

auth_bp = Blueprint("auth", __name__)


def _account_payload(user):
    """User plus role-specific details (used by /me, login and register)."""
    data = {"user": user.to_dict()}
    if user.profile is not None:
        data["profile"] = user.profile.to_dict()
        data["application"] = user.profile.application.to_dict(include_notes=False)
    if user.admin is not None:
        data["admin"] = user.admin.to_dict()
    return data


@auth_bp.post("/register")
def register():
    """Register an applicant account. Required: email, password, first_name, last_name.
    Any other profile field may be supplied now or later via PUT /api/applicant/profile."""
    user = auth_service.register_applicant(json_body())
    payload = _account_payload(user)
    payload.update(auth_service.issue_tokens(user))
    return success(payload, "Registration successful.", 201)


@auth_bp.post("/login")
def login():
    data = json_body()
    user = auth_service.authenticate(data.get("email"), data.get("password"))
    payload = _account_payload(user)
    payload.update(auth_service.issue_tokens(user))
    return success(payload, "Login successful.")


@auth_bp.post("/refresh")
def refresh():
    verify_jwt_in_request(refresh=True)
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None or not user.is_active:
        raise Unauthorized("This account is not available.")
    return success(auth_service.new_access_token(user))


@auth_bp.post("/logout")
def logout():
    """Revoke the access token in the Authorization header. Optionally send
    {"refresh_token": "..."} to revoke the refresh token too."""
    verify_jwt_in_request()
    user = db.session.get(User, int(get_jwt_identity()))
    body = request.get_json(silent=True) or {}
    refresh_token = body.get("refresh_token") if isinstance(body, dict) else None
    auth_service.logout(get_jwt(), user, refresh_token)
    return success(message="Logged out.")


@auth_bp.get("/me")
@role_required()
def me():
    return success(_account_payload(current_user()))


@auth_bp.patch("/me")
@role_required()
def update_me():
    """Change login email: {"email": "...", "current_password": "..."}."""
    user = auth_service.update_account(current_user(), json_body())
    return success(_account_payload(user), "Account updated.")


@auth_bp.post("/change-password")
@role_required()
def change_password():
    """{"current_password": "...", "new_password": "..."}. Revokes the current token."""
    auth_service.change_password(current_user(), json_body(), get_jwt())
    return success(message="Password changed. Please log in again.")
