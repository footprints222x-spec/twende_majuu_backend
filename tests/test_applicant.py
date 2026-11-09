import io

from tests.conftest import JPG_BYTES, PDF_BYTES, PNG_BYTES, auth, make_docx_bytes


def test_get_and_update_profile(client, make):
    data = make.applicant()
    h = auth(data["access_token"])
    assert client.get("/api/applicant/profile", headers=h).get_json()["data"]["first_name"] == "Amina"

    resp = client.patch("/api/applicant/profile", headers=h, json={
        "position_applied": "Captain", "years_experience": "12", "biography": None,
        "user_id": 999, "id": 999})  # mass-assignment attempt is ignored
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["position_applied"] == "Captain" and body["years_experience"] == 12
    assert body["biography"] is None and body["user_id"] == data["user"]["id"]

    put = client.put("/api/applicant/profile", headers=h, json={"phone": "+254700000000"})
    assert put.status_code == 200 and put.get_json()["data"]["phone"] == "+254700000000"


def test_profile_validation_and_non_clearable_names(client, make):
    h = auth(make.applicant()["access_token"])
    resp = client.patch("/api/applicant/profile", headers=h, json={
        "first_name": "", "phone": "abc", "date_of_birth": "12/04/1995", "passport_number": "!!"})
    assert resp.status_code == 422
    assert set(resp.get_json()["error"]["details"]) == {"first_name", "phone", "date_of_birth", "passport_number"}


def test_profile_passport_uniqueness(client, make):
    make.applicant(passport_number="TAKEN12345")
    h = auth(make.applicant()["access_token"])
    resp = client.patch("/api/applicant/profile", headers=h, json={"passport_number": "taken12345"})
    assert resp.status_code == 409


def test_application_status_overview(client, make):
    data = make.applicant()
    h = auth(data["access_token"])
    ov = client.get("/api/applicant/application", headers=h).get_json()["data"]
    assert ov["application"]["status"] == "pending"
    assert ov["application"]["status_label"] == "Pending"
    assert "admin_notes" not in ov["application"]
    assert ov["checklist"] == {"cv": False, "passport_photo": False, "passport_copy": False}
    make.upload(data["access_token"], "cv", "cv.pdf", PDF_BYTES)
    ov = client.get("/api/applicant/application", headers=h).get_json()["data"]
    assert ov["checklist"]["cv"] is True and ov["documents_count"] == 1


def test_upload_each_document_type(client, make, storage):
    t = make.applicant()["access_token"]
    make.upload(t, "cv", "my cv.docx", make_docx_bytes())
    make.upload(t, "passport_photo", "me.png", PNG_BYTES)
    make.upload(t, "passport_copy", "passport.jpg", JPG_BYTES)
    make.upload(t, "professional_certificate", "food-safety.pdf", PDF_BYTES)
    make.upload(t, "maritime_certificate", "stcw.pdf", PDF_BYTES)
    make.upload(t, "other", "ref.pdf", PDF_BYTES)
    items = client.get("/api/applicant/documents", headers=auth(t)).get_json()["data"]["items"]
    assert len(items) == 6
    # no URLs or storage identifiers are ever exposed
    dumped = str(items)
    assert "http" not in dumped and "public_id" not in dumped and "storage" not in dumped


def test_upload_validation(client, make):
    t = make.applicant()["access_token"]
    # disallowed extension for type
    assert make.upload(t, "cv", "cv.png", PNG_BYTES, expect=422)
    assert make.upload(t, "passport_photo", "photo.pdf", PDF_BYTES, expect=422)
    assert make.upload(t, "other", "virus.exe", b"MZ" + b"\x00" * 10, expect=422)
    # extension lies about contents
    assert make.upload(t, "cv", "fake.pdf", b"MZ not a pdf", expect=422)
    assert make.upload(t, "cv", "fake.docx", b"PK\x03\x04junk", expect=422)
    assert make.upload(t, "passport_photo", "fake.png", JPG_BYTES, expect=422)
    # empty
    assert make.upload(t, "cv", "empty.pdf", b"", expect=422)
    # unknown type
    assert make.upload(t, "selfie", "a.png", PNG_BYTES, expect=422)


def test_upload_size_limits(client, make, app):
    t = make.applicant()["access_token"]
    big_image = PNG_BYTES + b"\x00" * (5 * 1024 * 1024)
    make.upload(t, "passport_photo", "big.png", big_image, expect=413)
    big_pdf = PDF_BYTES + b"\x00" * (10 * 1024 * 1024)
    make.upload(t, "cv", "big.pdf", big_pdf, expect=413)
    # a request body far over the hard cap is rejected before parsing
    huge = PDF_BYTES + b"\x00" * (13 * 1024 * 1024)
    make.upload(t, "cv", "huge.pdf", huge, expect=413)


def test_missing_file_field(client, make):
    t = make.applicant()["access_token"]
    resp = client.post("/api/applicant/documents", headers=auth(t), data={"document_type": "cv"},
                       content_type="multipart/form-data")
    assert resp.status_code == 422


def test_single_document_types_replace_previous(client, make, storage):
    t = make.applicant()["access_token"]
    first = make.upload(t, "cv", "v1.pdf", PDF_BYTES).get_json()["data"]
    second = make.upload(t, "cv", "v2.pdf", PDF_BYTES + b"v2").get_json()["data"]
    items = client.get("/api/applicant/documents", headers=auth(t)).get_json()["data"]["items"]
    assert [d["id"] for d in items] == [second["id"]]
    assert len(storage.deleted) == 1  # old asset removed from storage
    # multi-document types accumulate
    make.upload(t, "maritime_certificate", "a.pdf", PDF_BYTES)
    make.upload(t, "maritime_certificate", "b.pdf", PDF_BYTES)
    items = client.get("/api/applicant/documents", headers=auth(t)).get_json()["data"]["items"]
    assert len(items) == 3


def test_document_limit(client, make, app):
    app.config["MAX_DOCUMENTS_PER_APPLICANT"] = 2
    t = make.applicant()["access_token"]
    make.upload(t, "other", "1.pdf", PDF_BYTES)
    make.upload(t, "other", "2.pdf", PDF_BYTES)
    make.upload(t, "other", "3.pdf", PDF_BYTES, expect=409)


def test_storage_failure_returns_502_and_stores_nothing(client, make, storage):
    t = make.applicant()["access_token"]
    storage.fail_uploads = True
    make.upload(t, "cv", "cv.pdf", PDF_BYTES, expect=502)
    assert client.get("/api/applicant/documents", headers=auth(t)).get_json()["data"]["items"] == []


def test_download_own_document_streams_bytes(client, make):
    t = make.applicant()["access_token"]
    doc = make.upload(t, "cv", "cv.pdf", PDF_BYTES).get_json()["data"]
    resp = client.get(f"/api/applicant/documents/{doc['id']}/download", headers=auth(t))
    assert resp.status_code == 200
    assert resp.data == PDF_BYTES
    assert resp.mimetype == "application/pdf"
    assert "attachment" in resp.headers["Content-Disposition"] and "cv.pdf" in resp.headers["Content-Disposition"]
    assert resp.headers["Cache-Control"] == "private, no-store"
    assert client.get(f"/api/applicant/documents/{doc['id']}/download").status_code == 401


def test_cannot_access_another_applicants_document(client, make):
    owner = make.applicant()["access_token"]
    other = make.applicant()["access_token"]
    doc = make.upload(owner, "passport_copy", "p.pdf", PDF_BYTES).get_json()["data"]
    assert client.get(f"/api/applicant/documents/{doc['id']}/download", headers=auth(other)).status_code == 404
    assert client.delete(f"/api/applicant/documents/{doc['id']}", headers=auth(other)).status_code == 404
    assert client.get(f"/api/applicant/documents/{doc['id']}/download", headers=auth(owner)).status_code == 200


def test_delete_own_document(client, make, storage):
    t = make.applicant()["access_token"]
    doc = make.upload(t, "other", "x.pdf", PDF_BYTES).get_json()["data"]
    assert client.delete(f"/api/applicant/documents/{doc['id']}", headers=auth(t)).status_code == 200
    assert client.get("/api/applicant/documents", headers=auth(t)).get_json()["data"]["items"] == []
    assert len(storage.deleted) == 1 and not storage.files
