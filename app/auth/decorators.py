"""Role-based authorisation.

`role_required` verifies the access token, re-loads the user from the database
(so a deactivated account loses access immediately, regardless of token age) and
checks the role. The role in the database is authoritative, not the token claim.
"""
from functools import wraps

from flask import g
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.errors import Forbidden, Unauthorized
from app.extensions import db
from app.models import User


def _load_user():
    try:
        user_id = int(get_jwt_identity())
    except (TypeError, ValueError):
        raise Unauthorized("Invalid token.")
    user = db.session.get(User, user_id)
    if user is None or not user.is_active:
        raise Unauthorized("This account is not available.")
    return user


def role_required(*roles):
    """Require a valid access token belonging to a user with one of `roles`."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = _load_user()
            if roles and user.role not in roles:
                raise Forbidden()
            g.current_user = user
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def current_user():
    """The authenticated User (set by role_required)."""
    return g.current_user
