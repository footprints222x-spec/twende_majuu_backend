from flask import jsonify, request

from app.errors import ValidationError


def success(data=None, message=None, status=200):
    """Standard success envelope: {"success": true, "message": ..., "data": ...}."""
    body = {"success": True}
    if message:
        body["message"] = message
    if data is not None:
        body["data"] = data
    return jsonify(body), status


def json_body():
    """Return the request JSON object or raise a 422."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValidationError({"body": "A JSON object body is required."}, message="Invalid request body.")
    return data
