# Twende Majuu – Crew Registration Backend

Flask + PostgreSQL REST API for an offshore cruise ship and yacht crew registration platform.
Applicants register, complete their profile, upload their documents and track their
application status. Administrators search, review, download documents and update statuses.

**Stack:** Flask · Flask-SQLAlchemy · Flask-Migrate · Flask-JWT-Extended · Flask-CORS · Cloudinary · python-dotenv · PostgreSQL

---

## 1. Quick start

Requires **Python 3.11+** and a running **PostgreSQL** server.

```bash
# 1. Virtual environment
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# 2. Dependencies
pip install -r requirements.txt

# 3. Configuration
cp .env.example .env                 # then edit .env (see sections 2 and 3)

# 4. Database tables
flask db upgrade

# 5. First administrator
flask create-admin

# 6. Run
flask run                            # http://127.0.0.1:5000
```

Check it works: `curl http://127.0.0.1:5000/api/health`

---

## 2. Configure PostgreSQL

Create a database and a dedicated user (using `psql` as the postgres superuser):

```sql
CREATE USER twende WITH PASSWORD 'choose-a-strong-password';
CREATE DATABASE twende_majuu OWNER twende;
```

Then set the connection string in `.env`:

```
DATABASE_URL=postgresql://twende:choose-a-strong-password@localhost:5432/twende_majuu
```

(Special characters in the password must be URL-encoded. Hosted providers that give a
`postgres://…` URL work as-is; it is converted automatically.)

## 3. Configure Cloudinary

1. Create a free account at <https://cloudinary.com>.
2. Open **Console → Settings → API Keys** and copy the cloud name, API key and API secret.
3. Put them in `.env`:

```
CLOUDINARY_CLOUD_NAME=...
CLOUDINARY_API_KEY=...
CLOUDINARY_API_SECRET=...
```

**How documents are kept private.** *Every* upload (CV, passport photo, passport copy,
certificates) is stored as a Cloudinary **`authenticated`** asset, which Cloudinary will not
serve from a plain URL. The database stores only metadata and the asset id, never a URL. To
download, the API checks the caller's permission, creates a signed link that expires after
2 minutes, fetches the file **server-side**, and streams it to the caller. The browser never
receives a Cloudinary URL. Files get random, unguessable names and live under
`twende-majuu/applicants/<id>/…`.

Generate the two secrets in `.env` with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 4. Migrations

The initial migration is included in `migrations/`.

```bash
flask db upgrade                      # apply
# After you change a model:
flask db migrate -m "describe change"
flask db upgrade
```

## 5. Create the first administrator

```bash
flask create-admin
# prompts for email, full name and password (hidden, confirmed)

# or non-interactively:
flask create-admin --email you@example.com --full-name "Your Name" --password 'S3cretPass'
```

Administrators sign in with the normal `POST /api/auth/login` endpoint; the response contains
`"role": "admin"`. Public registration can only ever create applicants.

---

## 6. API reference

Base URL `http://127.0.0.1:5000`. Send `Authorization: Bearer <access_token>` on protected routes.

**Response format**

```json
{ "success": true,  "message": "optional", "data": { } }
{ "success": false, "error": { "code": "validation_error", "message": "…", "details": { "email": "…" } } }
```

Status codes: `200` OK · `201` created · `401` missing/invalid/expired/revoked token or bad login ·
`403` wrong role / deactivated · `404` not found · `409` duplicate (email, passport) ·
`413` file too large · `422` validation error · `502` file storage unavailable · `503` storage not configured.

### Public

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness + database check |
| GET | `/api/options` | Genders, suggested positions, statuses, document types and allowed extensions (for building forms) |

### Authentication – `/api/auth`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/register` | – | Create applicant account. Required: `email`, `password`, `first_name`, `last_name`. Any profile field may be included. Returns user, profile, application and tokens. |
| POST | `/login` | – | `{email, password}` → user + `access_token` + `refresh_token` |
| POST | `/refresh` | refresh token | New access token |
| POST | `/logout` | access token | Revokes the token. Optional body `{"refresh_token": "…"}` revokes it too |
| GET | `/me` | any | Current account (+ profile/application, or admin details) |
| PATCH | `/me` | any | Change login email: `{email, current_password}` |
| POST | `/change-password` | any | `{current_password, new_password}` (current session is logged out) |

Passwords: 8–128 characters with at least one letter and one number.

### Applicant – `/api/applicant` (role: applicant)

| Method | Path | Purpose |
|---|---|---|
| GET | `/profile` | Own profile (`is_complete` and `missing_fields` tell the UI what is left) |
| PUT / PATCH | `/profile` | Partial update – send only the fields to change |
| GET | `/documents` | List own documents (metadata only) |
| POST | `/documents` | Upload. `multipart/form-data`: `document_type` + `file` |
| GET | `/documents/<id>/download` | Download own document |
| DELETE | `/documents/<id>` | Delete own document |
| GET | `/application` | Status + checklist of key documents |

**Profile fields:** `first_name`, `last_name`, `phone` (e.g. `+254712345678`), `date_of_birth`
(`YYYY-MM-DD`, 18+), `gender` (`male|female|other|prefer_not_to_say`), `nationality`,
`country_of_residence`, `address`, `passport_number`, `passport_expiry` (`YYYY-MM-DD`, not expired),
`position_applied`, `years_experience` (0–60), `biography` (≤ 2000 chars).

**Document types and limits**

| `document_type` | Allowed files | Behaviour |
|---|---|---|
| `cv` | PDF, DOCX | one; a new upload replaces the old one |
| `passport_photo` | JPG, PNG | one; replaces |
| `passport_copy` | PDF, JPG, PNG | one; replaces |
| `professional_certificate` | PDF, JPG, PNG | many |
| `maritime_certificate` | PDF, JPG, PNG | many |
| `other` | PDF, DOCX, JPG, PNG | many |

Images ≤ **5 MB**, PDF/DOCX ≤ **10 MB**, max **25** documents per applicant (all configurable in `.env`).
File contents are checked against the extension (magic bytes), so a renamed `.exe` is rejected.

### Admin – `/api/admin` (role: admin)

| Method | Path | Purpose |
|---|---|---|
| GET | `/applicants` | Paginated list (see filters below) |
| GET | `/applicants/<id>` | Full profile, application (with admin notes) and document list |
| DELETE | `/applicants/<id>` | Delete account, profile, application and stored files |
| GET | `/documents/<id>/download` | Securely download any document |
| PUT / PATCH | `/applications/<id>/status` | `{status, admin_notes?}` |
| GET | `/dashboard/stats` | Totals, registrations (24h/7d/30d), counts by status, top positions and nationalities, profiles complete, applicants with a CV, average experience |

`<id>` in `/applicants/<id>` is the **applicant profile id**; `/applications/<id>` uses the
**application id**. Both appear in the list response (`id` and `application_id`).

**List query parameters:** `q` (words must each match first name, last name, email or position),
`nationality` (contains, case-insensitive), `position` (contains), `status`
(`pending|under_review|shortlisted|approved|rejected`), `min_experience`, `max_experience`,
`sort_by` (`created_at|last_name|first_name|years_experience|status`), `order` (`asc|desc`),
`page`, `per_page` (max 100).

### Example session

```bash
B=http://127.0.0.1:5000/api

# Register (returns tokens)
curl -X POST $B/auth/register -H 'Content-Type: application/json' -d '{
  "email":"amina@example.com","password":"Passw0rd1",
  "first_name":"Amina","last_name":"Odhiambo","position_applied":"Chef","years_experience":6}'

# Upload a CV
curl -X POST $B/applicant/documents -H "Authorization: Bearer $TOKEN" \
  -F document_type=cv -F file=@cv.pdf

# Admin: shortlist an applicant
curl -X PATCH $B/admin/applications/1/status -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' -d '{"status":"shortlisted","admin_notes":"Strong galley CV"}'
```

### Connecting the React frontend

- Add your frontend origin(s) to `CORS_ORIGINS` (comma separated). Vite (`5173`) and CRA (`3000`) on localhost are preset.
- Keep `access_token` in memory (or your state manager) and call `/api/auth/refresh` with the refresh token when you get a `token_expired` error.
- Downloads need the Authorization header, so use `fetch` and turn the response into a blob:

```js
const res = await fetch(`${API}/applicant/documents/${id}/download`, {
  headers: { Authorization: `Bearer ${token}` },
});
const url = URL.createObjectURL(await res.blob());
// <a href={url} download="cv.pdf"> … or window.open(url)
```

- Uploads: `const f = new FormData(); f.append("document_type","cv"); f.append("file", file);` – do **not** set `Content-Type` yourself.

---

## 7. Project layout

```
app/
  __init__.py          application factory
  config.py            configuration from environment variables
  extensions.py        db, migrate, jwt, cors
  errors.py            JSON error types + handlers
  cli.py               flask create-admin, flask purge-expired-tokens
  models/              User, ApplicantProfile, Document, Application, Admin, TokenBlocklist
  auth/                role-based decorators, JWT callbacks, token revocation
  routes/              Blueprints: auth, applicant, admin, meta
  services/            business logic: auth, applicant, document, admin, storage (Cloudinary)
  utils/               validators, upload validation, response helpers
migrations/            Alembic migrations
tests/                 pytest suite (43 tests)
wsgi.py                entry point
```

Routes are thin; rules live in `services/`.

## 8. Tests

```bash
pip install -r requirements-dev.txt
pytest                                                    # in-memory SQLite, Cloudinary faked
TEST_DATABASE_URL=postgresql://user:pw@localhost/test_db pytest   # against PostgreSQL
```

The suite never touches Cloudinary; it swaps in an in-memory fake. Use an empty test database –
tables are created and dropped by the tests.

## 9. Security notes

- Passwords hashed with Werkzeug (scrypt); unknown-email logins take the same time and return the same message as wrong passwords.
- Role checks re-read the user from the database on each request, so deactivating or deleting an account takes effect immediately, not when the token expires.
- Logout and password change revoke tokens (blocklist table). Run `flask purge-expired-tokens` occasionally (e.g. a weekly cron) to tidy it.
- An applicant asking for another applicant's document gets `404`, not `403`.
- Admin list views omit passport number, address and date of birth; those appear only in the single-applicant detail view. Admin views, deletions, status changes and document downloads are written to the application log (`ADMIN_AUDIT …`).
- In production (`APP_ENV=production`) the app refuses to start with default or short secrets.
- All responses carry `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY`.

## 10. Production checklist

- `APP_ENV=production`, strong `SECRET_KEY` / `JWT_SECRET_KEY`, `CORS_ORIGINS` set to your real frontend domain only.
- Run behind HTTPS with gunicorn: `gunicorn -w 3 -b 0.0.0.0:8000 wsgi:app`.
- **Add rate limiting** (e.g. at your reverse proxy, or Flask-Limiter) on `/api/auth/login` and `/api/auth/register`. It is intentionally not included to keep dependencies to the requested stack.
- Passport numbers are stored as plain text in the database (protected by access control, not encryption). If your legal or insurance requirements call for encryption at rest, add column-level encryption or rely on encrypted database storage.
- Back up the database; Cloudinary assets are separate from database backups.
- Consider your obligations under data-protection law (e.g. Kenya's Data Protection Act, GDPR) for collecting passport data: retention periods, consent wording and a way for applicants to request deletion (admins can already delete via the API).
# twende_majuu_backend
