"""Consistent JSON errors.

Every error response looks like:
    {"success": false, "error": {"code": "...", "message": "...", "details": {...}}}
"""
from flask import jsonify
from werkzeug.exceptions import HTTPException


class APIError(Exception):
    status_code = 400
    code = "bad_request"
    default_message = "Bad request."

    def __init__(self, message=None, *, details=None, code=None, status_code=None):
        super().__init__(message or self.default_message)
        self.message = message or self.default_message
        self.details = details
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class ValidationError(APIError):
    status_code = 422
    code = "validation_error"
    default_message = "Validation failed."

    def __init__(self, details=None, message=None):
        super().__init__(message, details=details)


class Unauthorized(APIError):
    status_code = 401
    code = "unauthorized"
    default_message = "Authentication required."


class Forbidden(APIError):
    status_code = 403
    code = "forbidden"
    default_message = "You do not have permission to perform this action."


class NotFound(APIError):
    status_code = 404
    code = "not_found"
    default_message = "Resource not found."


class Conflict(APIError):
    status_code = 409
    code = "conflict"
    default_message = "Resource already exists."


class PayloadTooLarge(APIError):
    status_code = 413
    code = "payload_too_large"
    default_message = "The uploaded file is too large."


class StorageError(APIError):
    status_code = 502
    code = "storage_error"
    default_message = "The file storage service is unavailable. Please try again."


def error_response(status_code, code, message, details=None):
    body = {"success": False, "error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return jsonify(body), status_code


def register_error_handlers(app):
    from .extensions import db

    @app.errorhandler(APIError)
    def handle_api_error(err):
        return error_response(err.status_code, err.code, err.message, err.details)

    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        code = (err.name or "error").lower().replace(" ", "_")
        message = err.description
        if err.code == 413:
            message = "The request body is too large."
        return error_response(err.code or 500, code, message)

    @app.errorhandler(Exception)
    def handle_unexpected(err):
        app.logger.exception("Unhandled error: %s", err)
        db.session.rollback()
        return error_response(500, "internal_error", "An unexpected error occurred.")
