# TrustVault

TrustVault is an existing Django document-drive application with private uploads, server-enforced sharing, and an audit trail. It uses the configured custom user model `core.User`, SQLite for local development, and PostgreSQL when `DATABASE_URL` uses a PostgreSQL URL.

## Features

- Accounts with `ADMIN`, `OWNER`, and `RECIPIENT` roles; registration creates an owner.
- Upload any file extension (no PDF-only allowlist); the default per-file limit is 25 MiB and is configurable with `MAX_UPLOAD_SIZE` in bytes.
- Original filenames are retained for display. Stored paths use random server-generated names under private storage.
- No public upload URL or in-browser preview. Authorized downloads use attachment disposition, `application/octet-stream`, and `X-Content-Type-Options: nosniff`.
- Owners and admins manage `READ` and `EDIT` grants. `READ` permits viewing/downloading only; `EDIT` also permits the current text-content editor. Rename, delete, star changes, and sharing remain owner/admin operations.
- Revocation is POST-only, CSRF-protected, and checked on every document request.
- Audit events cover authentication, upload, view, download, permission changes, revocation, deletion/restoration, and denied access.

## Requirements

- Python 3.11 or later
- Django 5.2
- PostgreSQL for production; SQLite is used by default locally
- `requirements.txt` dependencies for production: Gunicorn, Psycopg, and WhiteNoise

## Local setup (PowerShell)

From the project root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Settings are read from process environment variables. `.env.example` is a reference for values; the application does not parse `.env` automatically. Set local values for the current PowerShell session (the development secret shown here is intentionally not a production secret):

```powershell
$env:TRUSTVAULT_SECRET_KEY = 'local-only-change-this'
$env:TRUSTVAULT_DEBUG = '1'
$env:TRUSTVAULT_ALLOWED_HOSTS = 'localhost,127.0.0.1'
```

Then prepare the database and run the app:

```powershell
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. The existing `db.sqlite3` is local user data; migrations update its schema and do not reset it. Do not delete it as a setup step.

## Accounts and demo data

- Create normal accounts through `/register/`; no demo account or automatic login is created.
- For local administrator access, run `python manage.py createsuperuser`. To enable the application's custom ADMIN role, sign into Django admin and set that user's `role` to `ADMIN`, or use `python manage.py shell` to update the role. Django superuser status and the TrustVault `role` are separate fields.
- Register a second account to demonstrate sharing. Keep all passwords local and out of source control.
- For repeatable demo steps, see [DEMO.md](DEMO.md).

## Environment variables

- `TRUSTVAULT_SECRET_KEY`: secret key; required when `TRUSTVAULT_DEBUG=0`.
- `TRUSTVAULT_DEBUG`: `1` locally; set `0` in production.
- `TRUSTVAULT_ALLOWED_HOSTS`: comma-separated hostnames.
- `DATABASE_URL`: `sqlite:///db.sqlite3` locally, or `postgresql://USER:PASSWORD@HOST:5432/DBNAME` in production.
- `DATABASE_SSLMODE`: PostgreSQL SSL mode; defaults to `require` outside debug mode.
- `MAX_UPLOAD_SIZE`: maximum bytes per file; defaults to `26214400` (25 MiB).
- `PRIVATE_STORAGE_ROOT`: private persistent directory; defaults to `private_storage` under the project root.
- `TRUSTVAULT_SECURE_SSL_REDIRECT`: defaults on when debug is off.
- `TRUSTVAULT_CSRF_TRUSTED_ORIGINS`: comma-separated full origins when required by the host.
- `TRUSTVAULT_USE_X_FORWARDED_PROTO`: set to `1` only behind a trusted HTTPS-terminating proxy.
- `TRUSTVAULT_HSTS_SECONDS`, `TRUSTVAULT_HSTS_SUBDOMAINS`, `TRUSTVAULT_HSTS_PRELOAD`: production HSTS controls. Enable long HSTS only after HTTPS is confirmed.

## Database and migrations

SQLite is the default and preserves the existing local database. Set `DATABASE_URL` to PostgreSQL for production, install the dependencies in `requirements.txt`, and run `python manage.py migrate`. Do not commit either database. No seed command is provided; create accounts interactively as described above.

## Tests and checks

```powershell
python manage.py check
python manage.py test core.tests
```

## Upload/storage behavior

The server accepts arbitrary extensions and does not treat the browser's file picker as validation. The size check is performed against the uploaded file on the server. Files are stored below `PRIVATE_STORAGE_ROOT/documents/`, never under `static/` or a public media route. Production storage must be durable and private: configure a persistent disk, restrict filesystem access to the application, and back it up independently. Downloads are attachment-only; file contents are not scanned for malware and are never executed by TrustVault.

## Audit limitations

The application writes a SHA-256-linked audit chain and its Django admin screen is read-only. The chain can detect some edits when verified, but it is not tamper-proof: an administrator with database or filesystem-level database access can alter rows and recompute the chain. There is no external immutable log sink or independent append-only storage.

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for the prepared Render + PostgreSQL deployment procedure. This repository has not been deployed or verified against a live host.
