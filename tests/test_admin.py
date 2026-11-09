from click.testing import CliRunner

from tests.conftest import PDF_BYTES, PNG_BYTES, auth


def seed(make):
    a = make.applicant(first_name="Amina", last_name="Odhiambo", position_applied="Chef",
                       nationality="Kenyan", years_experience=6, email="amina@example.com")
    b = make.applicant(first_name="Bruno", last_name="Silva", position_applied="Deckhand",
                       nationality="Brazilian", years_experience=2, email="bruno@example.com")
    c = make.applicant(first_name="Chen", last_name="Wei", position_applied="Sous Chef",
                       nationality="Kenyan", years_experience=12, email="chen@example.com")
    return a, b, c


# ---- authorisation -------------------------------------------------------------------
ADMIN_ENDPOINTS = [
    ("get", "/api/admin/applicants"),
    ("get", "/api/admin/applicants/1"),
    ("delete", "/api/admin/applicants/1"),
    ("patch", "/api/admin/applications/1/status"),
    ("get", "/api/admin/dashboard/stats"),
    ("get", "/api/admin/documents/1/download"),
]


def test_admin_endpoints_reject_anonymous_and_applicants(client, make):
    applicant = make.applicant()["access_token"]
    for method, url in ADMIN_ENDPOINTS:
        assert getattr(client, method)(url).status_code == 401, url
        r = getattr(client, method)(url, headers=auth(applicant), json={"status": "approved"})
        assert r.status_code == 403, url


def test_applicant_endpoints_reject_admins(client, make):
    admin = make.admin()["access_token"]
    assert client.get("/api/applicant/profile", headers=auth(admin)).status_code == 403
    assert client.get("/api/applicant/application", headers=auth(admin)).status_code == 403


def test_admin_login_returns_admin_account(make):
    data = make.admin()
    assert data["user"]["role"] == "admin" and data["admin"]["full_name"] == "Test Admin"


# ---- list / search / filter -------------------------------------------------------------
def test_list_search_filter_and_pagination(client, make):
    seed(make)
    h = auth(make.admin()["access_token"])

    def ids(**params):
        r = client.get("/api/admin/applicants", headers=h, query_string=params)
        assert r.status_code == 200, r.get_json()
        return [i["last_name"] for i in r.get_json()["data"]["items"]]

    assert sorted(ids()) == ["Odhiambo", "Silva", "Wei"]
    assert ids(q="amina") == ["Odhiambo"]                      # first name
    assert ids(q="SILVA") == ["Silva"]                         # last name, case-insensitive
    assert ids(q="chen@example") == ["Wei"]                    # email
    assert sorted(ids(q="chef")) == ["Odhiambo", "Wei"]        # position (Chef + Sous Chef)
    assert ids(q="chen chef") == ["Wei"]                       # every word must match
    assert ids(q="100%") == []                                 # wildcard is escaped, not a match-all
    assert sorted(ids(nationality="kenyan")) == ["Odhiambo", "Wei"]
    assert ids(min_experience=5, max_experience=8) == ["Odhiambo"]
    assert ids(min_experience=10) == ["Wei"]
    assert ids(position="deck") == ["Silva"]
    assert ids(sort_by="years_experience", order="asc") == ["Silva", "Odhiambo", "Wei"]

    page = client.get("/api/admin/applicants", headers=h, query_string={"per_page": 2, "page": 2}).get_json()["data"]
    assert len(page["items"]) == 1
    assert page["pagination"] == {"page": 2, "per_page": 2, "total": 3, "pages": 2, "has_next": False, "has_prev": True}


def test_list_filter_by_status_and_bad_params(client, make):
    a, b, _ = seed(make)
    h = auth(make.admin()["access_token"])
    app_id = a["application"]["id"]
    client.patch(f"/api/admin/applications/{app_id}/status", headers=h, json={"status": "Under Review"})
    r = client.get("/api/admin/applicants", headers=h, query_string={"status": "under_review"}).get_json()["data"]
    assert [i["last_name"] for i in r["items"]] == ["Odhiambo"]
    for params in ({"status": "bogus"}, {"page": "x"}, {"per_page": 500}, {"sort_by": "password"},
                   {"order": "sideways"}, {"min_experience": "-1"}):
        assert client.get("/api/admin/applicants", headers=h, query_string=params).status_code == 422, params


def test_list_hides_sensitive_fields(client, make):
    seed(make)
    h = auth(make.admin()["access_token"])
    item = client.get("/api/admin/applicants", headers=h).get_json()["data"]["items"][0]
    for field in ("passport_number", "address", "date_of_birth", "passport_expiry"):
        assert field not in item


# ---- detail / documents ---------------------------------------------------------------------
def test_view_full_profile_and_download_document(client, make):
    a = make.applicant()
    make.upload(a["access_token"], "passport_copy", "pp.pdf", PDF_BYTES)
    make.upload(a["access_token"], "passport_photo", "me.png", PNG_BYTES)
    h = auth(make.admin()["access_token"])

    detail = client.get(f"/api/admin/applicants/{a['profile']['id']}", headers=h).get_json()["data"]
    assert detail["passport_number"] == a["profile"]["passport_number"]
    assert detail["application"]["status"] == "pending" and "admin_notes" in detail["application"]
    assert {d["document_type"] for d in detail["documents"]} == {"passport_copy", "passport_photo"}

    doc = next(d for d in detail["documents"] if d["document_type"] == "passport_copy")
    dl = client.get(f"/api/admin/documents/{doc['id']}/download", headers=h)
    assert dl.status_code == 200 and dl.data == PDF_BYTES
    assert "attachment" in dl.headers["Content-Disposition"]

    assert client.get("/api/admin/applicants/99999", headers=h).status_code == 404
    assert client.get("/api/admin/documents/99999/download", headers=h).status_code == 404


# ---- status ---------------------------------------------------------------------------------------
def test_update_status_flow(client, make):
    a = make.applicant()
    ah = auth(a["access_token"])
    h = auth(make.admin()["access_token"])
    app_id = a["application"]["id"]

    for status in ("under_review", "shortlisted", "approved", "rejected", "pending"):
        r = client.put(f"/api/admin/applications/{app_id}/status", headers=h,
                       json={"status": status, "admin_notes": f"note for {status}"})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["data"]["status"] == status
        assert r.get_json()["data"]["reviewed_by"] == "Test Admin"
    client.patch(f"/api/admin/applications/{app_id}/status", headers=h, json={"status": "approved"})

    # applicant sees the new status but never the internal notes
    ov = client.get("/api/applicant/application", headers=ah).get_json()["data"]["application"]
    assert ov["status"] == "approved" and ov["status_label"] == "Approved"
    assert "admin_notes" not in ov and "reviewed_by" not in ov

    # omitting admin_notes keeps the existing note
    detail = client.get(f"/api/admin/applicants/{a['profile']['id']}", headers=h).get_json()["data"]
    assert detail["application"]["admin_notes"] == "note for pending"


def test_update_status_validation(client, make):
    a = make.applicant()
    h = auth(make.admin()["access_token"])
    app_id = a["application"]["id"]
    assert client.patch(f"/api/admin/applications/{app_id}/status", headers=h, json={"status": "hired"}).status_code == 422
    assert client.patch(f"/api/admin/applications/{app_id}/status", headers=h, json={}).status_code == 422
    assert client.patch(f"/api/admin/applications/{app_id}/status", headers=h,
                        json={"status": "approved", "admin_notes": 5}).status_code == 422
    assert client.patch("/api/admin/applications/99999/status", headers=h, json={"status": "approved"}).status_code == 404


# ---- delete ----------------------------------------------------------------------------------------
def test_delete_applicant_removes_everything(client, make, storage, app):
    from app.models import ApplicantProfile, Application, Document, User

    a = make.applicant(email="del@example.com")
    make.upload(a["access_token"], "cv", "cv.pdf", PDF_BYTES)
    make.upload(a["access_token"], "passport_photo", "p.png", PNG_BYTES)
    keep = make.applicant(email="keep@example.com")
    make.upload(keep["access_token"], "cv", "cv.pdf", PDF_BYTES)
    h = auth(make.admin()["access_token"])

    assert client.delete(f"/api/admin/applicants/{a['profile']['id']}", headers=h).status_code == 200
    assert User.query.filter_by(email="del@example.com").first() is None
    assert ApplicantProfile.query.count() == 1 and Application.query.count() == 1 and Document.query.count() == 1
    assert len(storage.deleted) == 2 and len(storage.files) == 1
    assert client.get(f"/api/admin/applicants/{a['profile']['id']}", headers=h).status_code == 404
    # deleted applicant's tokens no longer work
    assert client.get("/api/auth/me", headers=auth(a["access_token"])).status_code == 401
    assert client.delete(f"/api/admin/applicants/{a['profile']['id']}", headers=h).status_code == 404


# ---- stats --------------------------------------------------------------------------------------------
def test_dashboard_stats(client, make):
    a, b, c = seed(make)
    make.upload(a["access_token"], "cv", "cv.pdf", PDF_BYTES)
    h = auth(make.admin()["access_token"])
    client.patch(f"/api/admin/applications/{b['application']['id']}/status", headers=h, json={"status": "approved"})
    stats = client.get("/api/admin/dashboard/stats", headers=h).get_json()["data"]
    assert stats["total_applicants"] == 3
    by = {s["status"]: s["count"] for s in stats["by_status"]}
    assert by == {"pending": 2, "under_review": 0, "shortlisted": 0, "approved": 1, "rejected": 0}
    assert stats["registrations"]["last_24_hours"] == 3
    assert stats["top_nationalities"][0] == {"name": "Kenyan", "count": 2}
    assert {p["name"] for p in stats["top_positions"]} == {"Chef", "Deckhand", "Sous Chef"}
    assert stats["profiles_complete"] == 3 and stats["applicants_with_cv"] == 1
    assert stats["average_years_experience"] == 6.7


def test_stats_empty_database(client, make):
    h = auth(make.admin()["access_token"])
    stats = client.get("/api/admin/dashboard/stats", headers=h).get_json()["data"]
    assert stats["total_applicants"] == 0 and stats["average_years_experience"] is None


# ---- CLI --------------------------------------------------------------------------------------------------
def test_create_admin_cli(app, client):
    runner = app.test_cli_runner()
    res = runner.invoke(args=["create-admin", "--email", "Boss@Example.com", "--full-name", "The Boss",
                              "--password", "Sup3rSecret"])
    assert res.exit_code == 0, res.output
    login = client.post("/api/auth/login", json={"email": "boss@example.com", "password": "Sup3rSecret"})
    assert login.status_code == 200 and login.get_json()["data"]["user"]["role"] == "admin"

    dup = runner.invoke(args=["create-admin", "--email", "boss@example.com", "--full-name", "X", "--password", "Sup3rSecret"])
    assert dup.exit_code != 0 and "already exists" in dup.output
    weak = runner.invoke(args=["create-admin", "--email", "x@example.com", "--full-name", "X", "--password", "weak"])
    assert weak.exit_code != 0


def test_purge_expired_tokens_cli(app, client, make):
    from app.extensions import db
    from app.models import TokenBlocklist
    from datetime import datetime, timedelta, timezone

    db.session.add(TokenBlocklist(jti="old", token_type="access",
                                  expires_at=datetime.now(timezone.utc) - timedelta(days=1)))
    db.session.commit()
    res = app.test_cli_runner().invoke(args=["purge-expired-tokens"])
    assert res.exit_code == 0 and "Removed 1" in res.output
