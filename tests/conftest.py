import io
import itertools
import zipfile

import pytest

from app import create_app
from app.extensions import db
from app.models import Admin, User
from app.models.constants import ROLE_ADMIN
from app.services import storage_service

# ---- sample files -----------------------------------------------------------------
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def make_docx_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


class FakeUpstream:
    def __init__(self, data):
        self._data = data
        self.closed = False

    def iter_content(self, chunk_size=1024):
        for i in range(0, len(self._data), chunk_size):
            yield self._data[i : i + chunk_size]

    def close(self):
        self.closed = True


class FakeStorage:
    """In-memory stand-in for Cloudinary."""

    def __init__(self):
        self.files = {}  # public_id -> bytes
        self.deleted = []
        self.fail_uploads = False
        self._ids = itertools.count(1)

    def upload_private(self, data, *, folder, extension, resource_type):
        if self.fail_uploads:
            from app.errors import StorageError

            raise StorageError()
        public_id = f"{folder}/{next(self._ids)}" + (f".{extension}" if resource_type == "raw" else "")
        self.files[public_id] = data
        fmt = extension if resource_type == "image" else None
        return storage_service.StoredFile(public_id, resource_type, fmt)

    def delete_file(self, public_id, resource_type):
        self.files.pop(public_id, None)
        self.deleted.append(public_id)

    def fetch_stream(self, document):
        return FakeUpstream(self.files[document.storage_public_id])


@pytest.fixture
def storage(monkeypatch):
    fake = FakeStorage()
    monkeypatch.setattr(storage_service, "upload_private", fake.upload_private)
    monkeypatch.setattr(storage_service, "delete_file", fake.delete_file)
    monkeypatch.setattr(storage_service, "fetch_stream", fake.fetch_stream)
    return fake


@pytest.fixture
def app(storage):
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


# ---- helpers -----------------------------------------------------------------------
def auth(token):
    return {"Authorization": f"Bearer {token}"}


FULL_PROFILE = {
    "first_name": "Amina",
    "last_name": "Odhiambo",
    "phone": "+254712345678",
    "date_of_birth": "1995-04-12",
    "gender": "female",
    "nationality": "Kenyan",
    "country_of_residence": "Kenya",
    "address": "12 Moi Avenue, Mombasa",
    "passport_number": "AK1234567",
    "passport_expiry": "2032-01-31",
    "position_applied": "Chef",
    "years_experience": 6,
    "biography": "Cruise-line galley experience.",
}


class Factory:
    def __init__(self, client, app):
        self.client = client
        self.app = app
        self._n = 0

    def applicant(self, **overrides):
        """Register an applicant; returns (tokens, response_data)."""
        self._n += 1
        payload = {
            "email": f"user{self._n}@example.com",
            "password": "Passw0rdOK",
            **FULL_PROFILE,
            "passport_number": f"PP{1000000 + self._n}",
        }
        payload.update(overrides)
        resp = self.client.post("/api/auth/register", json=payload)
        assert resp.status_code == 201, resp.get_json()
        return resp.get_json()["data"]

    def admin(self, email="admin@example.com", password="AdminPass1"):
        user = User(email=email, role=ROLE_ADMIN)
        user.set_password(password)
        Admin(user=user, full_name="Test Admin")
        db.session.add(user)
        db.session.commit()
        resp = self.client.post("/api/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()["data"]

    def upload(self, token, doc_type, filename, content, expect=201):
        resp = self.client.post(
            "/api/applicant/documents",
            headers=auth(token),
            data={"document_type": doc_type, "file": (io.BytesIO(content), filename)},
            content_type="multipart/form-data",
        )
        assert resp.status_code == expect, resp.get_json()
        return resp


@pytest.fixture
def make(client, app):
    return Factory(client, app)
