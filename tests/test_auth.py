from tests.conftest import auth


def test_register_creates_account_profile_and_pending_application(client, make):
    data = make.applicant()
    assert data["user"]["role"] == "applicant"
    assert data["application"]["status"] == "pending"
    assert data["profile"]["is_complete"] is True
    assert data["access_token"] and data["refresh_token"]
    assert "password" not in str(data).lower().replace("password_hash", "")  # no hash leaked
    assert "password_hash" not in data["user"]


def test_register_minimal_then_profile_incomplete(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "Min@Example.com", "password": "Passw0rd1", "first_name": "Jo", "last_name": "Mwangi"},
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    assert data["user"]["email"] == "min@example.com"  # normalised
    assert data["profile"]["is_complete"] is False
    assert "passport_number" in data["profile"]["missing_fields"]


def test_register_validation_errors(client):
    resp = client.post(
        "/api/auth/register",
        json={"email": "nope", "password": "short", "first_name": "", "date_of_birth": "2015-01-01",
              "passport_expiry": "2001-01-01", "years_experience": 99, "gender": "x"},
    )
    assert resp.status_code == 422
    details = resp.get_json()["error"]["details"]
    for field in ("email", "password", "first_name", "last_name", "date_of_birth",
                  "passport_expiry", "years_experience", "gender"):
        assert field in details, field


def test_register_rejects_non_json(client):
    resp = client.post("/api/auth/register", data="hello", content_type="text/plain")
    assert resp.status_code == 422


def test_register_duplicate_email_and_passport(client, make):
    make.applicant(email="dup@example.com", passport_number="DUP123456")
    r1 = client.post("/api/auth/register", json={
        "email": "DUP@example.com", "password": "Passw0rd1", "first_name": "A", "last_name": "B"})
    assert r1.status_code == 409
    r2 = client.post("/api/auth/register", json={
        "email": "other@example.com", "password": "Passw0rd1", "first_name": "A", "last_name": "B",
        "passport_number": "dup 123456"})
    assert r2.status_code == 409


def test_login_success_and_failures(client, make):
    make.applicant(email="a@example.com", password="Passw0rd1")
    ok = client.post("/api/auth/login", json={"email": "A@example.com", "password": "Passw0rd1"})
    assert ok.status_code == 200 and ok.get_json()["data"]["access_token"]
    bad_pw = client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong"})
    unknown = client.post("/api/auth/login", json={"email": "zzz@example.com", "password": "Passw0rd1"})
    assert bad_pw.status_code == unknown.status_code == 401
    assert bad_pw.get_json()["error"]["message"] == unknown.get_json()["error"]["message"]


def test_me_requires_token_and_returns_account(client, make):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=auth("garbage")).status_code == 401
    data = make.applicant()
    resp = client.get("/api/auth/me", headers=auth(data["access_token"]))
    assert resp.status_code == 200
    assert resp.get_json()["data"]["user"]["email"] == data["user"]["email"]


def test_logout_revokes_access_and_refresh_tokens(client, make):
    data = make.applicant()
    resp = client.post("/api/auth/logout", headers=auth(data["access_token"]),
                       json={"refresh_token": data["refresh_token"]})
    assert resp.status_code == 200
    after = client.get("/api/auth/me", headers=auth(data["access_token"]))
    assert after.status_code == 401 and after.get_json()["error"]["code"] == "token_revoked"
    refresh = client.post("/api/auth/refresh", headers=auth(data["refresh_token"]))
    assert refresh.status_code == 401


def test_refresh_issues_working_access_token(client, make):
    data = make.applicant()
    resp = client.post("/api/auth/refresh", headers=auth(data["refresh_token"]))
    assert resp.status_code == 200
    new_access = resp.get_json()["data"]["access_token"]
    assert client.get("/api/auth/me", headers=auth(new_access)).status_code == 200
    # an access token cannot be used to refresh
    assert client.post("/api/auth/refresh", headers=auth(data["access_token"])).status_code == 401


def test_change_password(client, make):
    data = make.applicant(email="pw@example.com", password="OldPassw0rd")
    h = auth(data["access_token"])
    bad = client.post("/api/auth/change-password", headers=h,
                      json={"current_password": "nope", "new_password": "NewPassw0rd"})
    assert bad.status_code == 422
    weak = client.post("/api/auth/change-password", headers=h,
                       json={"current_password": "OldPassw0rd", "new_password": "weak"})
    assert weak.status_code == 422
    ok = client.post("/api/auth/change-password", headers=h,
                     json={"current_password": "OldPassw0rd", "new_password": "NewPassw0rd"})
    assert ok.status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401  # old token revoked
    assert client.post("/api/auth/login", json={"email": "pw@example.com", "password": "OldPassw0rd"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "pw@example.com", "password": "NewPassw0rd"}).status_code == 200


def test_change_email_requires_password_and_uniqueness(client, make):
    a = make.applicant(email="one@example.com", password="Passw0rd1")
    make.applicant(email="two@example.com")
    h = auth(a["access_token"])
    assert client.patch("/api/auth/me", headers=h, json={"email": "new@example.com", "current_password": "x"}).status_code == 422
    assert client.patch("/api/auth/me", headers=h, json={"email": "two@example.com", "current_password": "Passw0rd1"}).status_code == 409
    ok = client.patch("/api/auth/me", headers=h, json={"email": "New@Example.com", "current_password": "Passw0rd1"})
    assert ok.status_code == 200 and ok.get_json()["data"]["user"]["email"] == "new@example.com"


def test_deactivated_user_loses_access(client, make, app):
    from app.extensions import db
    from app.models import User

    data = make.applicant(email="gone@example.com", password="Passw0rd1")
    user = db.session.get(User, data["user"]["id"])
    user.is_active = False
    db.session.commit()
    assert client.get("/api/auth/me", headers=auth(data["access_token"])).status_code == 401
    assert client.post("/api/auth/login", json={"email": "gone@example.com", "password": "Passw0rd1"}).status_code == 403


def test_passwords_are_hashed(app, make):
    from app.models import User

    make.applicant(email="hash@example.com", password="Passw0rd1")
    user = User.query.filter_by(email="hash@example.com").one()
    assert "Passw0rd1" not in user.password_hash
    assert user.password_hash.startswith(("scrypt:", "pbkdf2:"))


def test_json_404_405_and_health(client):
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.get_json()["success"] is False
    r = client.delete("/api/auth/login")
    assert r.status_code == 405 and r.get_json()["success"] is False
    assert client.get("/api/health").get_json()["data"]["status"] == "ok"
    assert client.get("/api/options").status_code == 200


def test_cors_allows_configured_origin_only(client):
    ok = client.options("/api/auth/login", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type"})
    assert ok.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
    bad = client.options("/api/auth/login", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert "Access-Control-Allow-Origin" not in bad.headers
