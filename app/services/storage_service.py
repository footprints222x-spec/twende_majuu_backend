"""Cloudinary wrapper. Every asset is uploaded with type="authenticated", which
means Cloudinary refuses to deliver it from a plain URL. The only way to read a
file is through a signed, short-lived download URL generated here and fetched
server-side, so no usable link is ever sent to the browser."""
import io
import time
import uuid
from dataclasses import dataclass

import cloudinary
import cloudinary.exceptions
import cloudinary.uploader
import cloudinary.utils
import requests
from flask import current_app

from app.errors import APIError, StorageError


@dataclass
class StoredFile:
    public_id: str
    resource_type: str
    format: str | None


def configure_cloudinary(app):
    cloudinary.config(
        cloud_name=app.config.get("CLOUDINARY_CLOUD_NAME"),
        api_key=app.config.get("CLOUDINARY_API_KEY"),
        api_secret=app.config.get("CLOUDINARY_API_SECRET"),
        secure=True,
    )


def is_configured():
    cfg = current_app.config
    return all(cfg.get(k) for k in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"))


def _require_configured():
    if not is_configured():
        raise APIError(
            "File storage is not configured on the server.",
            status_code=503,
            code="storage_not_configured",
        )


def upload_private(data, *, folder, extension, resource_type):
    """Upload bytes as a private asset and return where it was stored."""
    _require_configured()
    name = uuid.uuid4().hex  # unguessable; never derived from user input
    # Raw assets keep their extension inside the public_id; images do not.
    public_id = f"{name}.{extension}" if resource_type == "raw" else name
    try:
        result = cloudinary.uploader.upload(
            io.BytesIO(data),
            type="authenticated",
            resource_type=resource_type,
            folder=f"{current_app.config['CLOUDINARY_FOLDER']}/{folder}",
            public_id=public_id,
            overwrite=False,
            unique_filename=False,
            use_filename=False,
        )
    except (cloudinary.exceptions.Error, requests.RequestException) as exc:
        current_app.logger.error("Cloudinary upload failed: %s", exc)
        raise StorageError("Could not store the file. Please try again.")
    return StoredFile(
        public_id=result["public_id"],
        resource_type=result.get("resource_type", resource_type),
        format=result.get("format"),
    )


def delete_file(public_id, resource_type):
    """Delete an asset. Raises StorageError on failure (callers decide whether that matters)."""
    _require_configured()
    try:
        cloudinary.uploader.destroy(
            public_id, resource_type=resource_type, type="authenticated", invalidate=True
        )
    except (cloudinary.exceptions.Error, requests.RequestException) as exc:
        raise StorageError(f"Could not delete {public_id}: {exc}")


def fetch_stream(document):
    """Open a streaming HTTP response for a stored document.

    Returns an object with `.iter_content(chunk_size)` and `.close()`.
    The signed URL is created here, used immediately, and never leaves the server.
    """
    _require_configured()
    ttl = current_app.config["DOWNLOAD_URL_TTL_SECONDS"]
    # Images are addressed as public_id + format; raw files carry the extension in public_id.
    is_image = document.storage_resource_type == "image"
    fmt = (document.storage_format or "") if is_image else ""
    url = cloudinary.utils.private_download_url(
        document.storage_public_id,
        fmt,
        resource_type=document.storage_resource_type,
        type="authenticated",
        attachment=True,
        expires_at=int(time.time()) + ttl,
    )
    try:
        upstream = requests.get(url, stream=True, timeout=(5, 30))
    except requests.RequestException as exc:
        current_app.logger.error("Cloudinary download failed: %s", exc)
        raise StorageError("Could not retrieve the file. Please try again.")
    if upstream.status_code != 200:
        current_app.logger.error(
            "Cloudinary download returned %s for document %s", upstream.status_code, document.id
        )
        upstream.close()
        raise StorageError("Could not retrieve the file. Please try again.")
    return upstream
