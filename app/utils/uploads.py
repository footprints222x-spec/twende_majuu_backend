"""Upload validation: extension whitelist per document type, size limits, and
a magic-byte check so a renamed file (e.g. an .exe called cv.pdf) is rejected.
The client-supplied MIME type is never trusted."""
import io
import zipfile
from dataclasses import dataclass

from flask import current_app
from werkzeug.utils import secure_filename

from app.errors import PayloadTooLarge, ValidationError
from app.models.constants import DOCUMENT_RULES

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png"}


@dataclass
class ValidatedUpload:
    data: bytes
    filename: str
    extension: str
    content_type: str
    size: int

    @property
    def resource_type(self):
        """Cloudinary resource type: images are 'image', everything else 'raw'."""
        return "image" if self.extension in IMAGE_EXTENSIONS else "raw"


def _matches_signature(extension, data):
    if extension == "pdf":
        return data.startswith(b"%PDF-")
    if extension in ("jpg", "jpeg"):
        return data.startswith(b"\xff\xd8\xff")
    if extension == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if extension == "docx":
        if not data.startswith(b"PK\x03\x04"):
            return False
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                return "word/document.xml" in archive.namelist()
        except zipfile.BadZipFile:
            return False
    return False


def _size_limit_bytes(extension):
    key = "MAX_IMAGE_SIZE_MB" if extension in IMAGE_EXTENSIONS else "MAX_DOCUMENT_SIZE_MB"
    return current_app.config[key] * 1024 * 1024


def validate_upload(file_storage, document_type):
    """Validate an uploaded werkzeug FileStorage for the given document type."""
    rules = DOCUMENT_RULES[document_type]
    allowed = rules["extensions"]

    if file_storage is None or not file_storage.filename:
        raise ValidationError({"file": "A file is required (multipart field named 'file')."})

    original = secure_filename(file_storage.filename)
    extension = original.rsplit(".", 1)[-1].lower() if "." in original else ""
    if extension not in allowed:
        raise ValidationError(
            {"file": f"{rules['label']} must be one of: {', '.join(e.upper() for e in allowed)}."}
        )

    limit = _size_limit_bytes(extension)
    data = file_storage.stream.read(limit + 1)
    if len(data) > limit:
        raise PayloadTooLarge(f"File exceeds the {limit // (1024 * 1024)} MB limit for .{extension} files.")
    if not data:
        raise ValidationError({"file": "The uploaded file is empty."})
    if not _matches_signature(extension, data):
        raise ValidationError({"file": f"The file contents do not match a valid .{extension} file."})

    if not original or original.startswith("."):
        original = f"{document_type}.{extension}"

    return ValidatedUpload(
        data=data,
        filename=original[:255],
        extension=extension,
        content_type=CONTENT_TYPES[extension],
        size=len(data),
    )
