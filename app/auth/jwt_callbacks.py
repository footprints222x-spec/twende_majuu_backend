"""JWT error handlers (all JSON, all 401) and token revocation for logout."""
from datetime import datetime, timezone

from app.errors import error_response
from app.extensions import db
from app.models import TokenBlocklist


def register_jwt_callbacks(jwt):
    @jwt.token_in_blocklist_loader
    def is_revoked(_header, payload):
        return (
            db.session.query(TokenBlocklist.id).filter_by(jti=payload["jti"]).first() is not None
        )

    @jwt.unauthorized_loader
    def missing_token(reason):
        return error_response(401, "authorization_required", "Missing or malformed Authorization header.")

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return error_response(401, "invalid_token", "The token is invalid.")

    @jwt.expired_token_loader
    def expired_token(_header, _payload):
        return error_response(401, "token_expired", "The token has expired. Please log in again.")

    @jwt.revoked_token_loader
    def revoked_token(_header, _payload):
        return error_response(401, "token_revoked", "The token has been revoked. Please log in again.")


def revoke_token(payload, user_id=None):
    """Add a decoded token payload to the blocklist (idempotent)."""
    jti = payload["jti"]
    if db.session.query(TokenBlocklist.id).filter_by(jti=jti).first():
        return
    db.session.add(
        TokenBlocklist(
            jti=jti,
            token_type=payload.get("type", "access"),
            user_id=user_id,
            expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )
    )
