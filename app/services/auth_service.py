from datetime import datetime, timezone

from flask_jwt_extended import create_access_token, create_refresh_token, decode_token
from flask_jwt_extended.exceptions import JWTExtendedException
from jwt.exceptions import PyJWTError
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from flask import current_app

from app.auth import revoke_token
from app.errors import Conflict, Forbidden, Unauthorized, ValidationError
from app.extensions import db
from app.models import ApplicantProfile, Application, User
from app.models.constants import ROLE_APPLICANT
from app.services import applicant_service
from app.utils import validators as v

# Used to burn the same CPU time when the email is unknown, so response timing
# does not reveal which emails are registered.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def find_user_by_email(email):
    return User.query.filter_by(email=email).first()


def register_applicant(data):
    """Create user + profile + application (status 'pending') in one transaction."""
    errors = {}
    try:
        account = v.validate_fields(data, {"email": v.email, "password": v.password})
    except ValidationError as exc:
        errors.update(exc.details)
        account = {}
    try:
        profile_data = v.validate_profile(data, creating=True)
    except ValidationError as exc:
        errors.update(exc.details)
        profile_data = {}
    if errors:
        raise ValidationError(errors)

    if find_user_by_email(account["email"]):
        raise Conflict("An account with this email already exists.", details={"email": "Already registered."})
    applicant_service.ensure_passport_unique(profile_data.get("passport_number"))

    user = User(email=account["email"], role=ROLE_APPLICANT)
    user.set_password(account["password"])
    profile = ApplicantProfile(user=user, **profile_data)
    Application(applicant=profile)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise Conflict("An account with these details already exists.")
    return user


def authenticate(email, password):
    """Return the user for valid credentials, otherwise raise a generic 401."""
    email = (email or "").strip().lower() if isinstance(email, str) else ""
    password = password if isinstance(password, str) else ""
    user = find_user_by_email(email) if email else None
    if user is None:
        user_ok = False
        check_password_hash(_DUMMY_HASH, password)
    else:
        user_ok = user.check_password(password)
    if not user_ok:
        raise Unauthorized("Invalid email or password.")
    if not user.is_active:
        raise Forbidden("This account has been deactivated.")
    user.last_login_at = datetime.now(timezone.utc)
    db.session.commit()
    return user


def issue_tokens(user):
    claims = {"role": user.role}
    access = create_access_token(identity=str(user.id), additional_claims=claims)
    refresh = create_refresh_token(identity=str(user.id), additional_claims=claims)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "expires_in": int(current_app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds()),
    }


def new_access_token(user):
    token = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": int(current_app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds()),
    }


def logout(current_payload, user, refresh_token=None):
    """Revoke the presented token and, optionally, the paired refresh token."""
    revoke_token(current_payload, user.id)
    if refresh_token:
        try:
            refresh_payload = decode_token(refresh_token)
        except (JWTExtendedException, PyJWTError):
            refresh_payload = None
        if refresh_payload and str(refresh_payload.get("sub")) == str(user.id):
            revoke_token(refresh_payload, user.id)
    db.session.commit()


def change_password(user, data, current_payload):
    current = data.get("current_password")
    if not isinstance(current, str) or not user.check_password(current):
        raise ValidationError({"current_password": "Current password is incorrect."})
    cleaned = v.validate_fields(data, {"new_password": v.password})
    if cleaned["new_password"] == current:
        raise ValidationError({"new_password": "Choose a password different from the current one."})
    user.set_password(cleaned["new_password"])
    revoke_token(current_payload, user.id)  # force a fresh login on this device
    db.session.commit()


def update_account(user, data):
    """Change the login email (requires the current password)."""
    if "email" not in data:
        raise ValidationError({"email": "This field is required."})
    cleaned = v.validate_fields(data, {"email": v.email})
    if not isinstance(data.get("current_password"), str) or not user.check_password(data["current_password"]):
        raise ValidationError({"current_password": "Current password is incorrect."})
    if cleaned["email"] != user.email:
        if find_user_by_email(cleaned["email"]):
            raise Conflict("That email is already in use.", details={"email": "Already registered."})
        user.email = cleaned["email"]
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            raise Conflict("That email is already in use.")
    return user
