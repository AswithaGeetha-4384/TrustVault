# TrustVault deployment guide (Render)

This is a deployment procedure, not evidence of a live deployment. Render provides managed PostgreSQL and persistent disks suitable for the application's database and private uploads.

## Prerequisites

- A Render account and a private repository connection.
- A Render PostgreSQL database.
- A Render persistent disk mounted at `/var/data/trustvault-private`.
- A generated secret stored in Render environment settings, never in the repository.

## Web service configuration

Create a Render Web Service for this repository with:

- Runtime: Python.
- Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`.
- Start command: `python manage.py migrate && gunicorn trustvault.wsgi:application --bind 0.0.0.0:$PORT`.
- Persistent disk mount path: `/var/data/trustvault-private`.

Use Render's internal PostgreSQL connection string for `DATABASE_URL`. The service and database should be in the same region. Confirm the database connection's TLS requirements before setting `DATABASE_SSLMODE`.

## Environment variables

Set these in Render's environment configuration:

- `TRUSTVAULT_SECRET_KEY`: generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` in a private local shell; paste directly into the host's secret manager.
- `TRUSTVAULT_DEBUG=0`.
- `TRUSTVAULT_ALLOWED_HOSTS`: the exact Render hostname, plus any custom domain.
- `DATABASE_URL`: Render PostgreSQL internal connection string.
- `DATABASE_SSLMODE=require` when supported by that database endpoint; otherwise follow the provider's documented TLS settings.
- `PRIVATE_STORAGE_ROOT=/var/data/trustvault-private`.
- `MAX_UPLOAD_SIZE=26214400` (25 MiB).
- `TRUSTVAULT_SECURE_SSL_REDIRECT=1`.
- `TRUSTVAULT_USE_X_FORWARDED_PROTO=1` only when the Render proxy is the trusted TLS terminator.
- `TRUSTVAULT_CSRF_TRUSTED_ORIGINS=https://your-service.onrender.com` and the HTTPS custom domain if applicable.
- `TRUSTVAULT_HSTS_SECONDS=31536000` only after HTTPS and the domain are verified; enable subdomains/preload only after confirming all subdomains are HTTPS-ready.

Do not set `ADMIN_EMAIL` as a substitute for an administrator account; the application does not create accounts automatically.

## First deployment and accounts

1. Deploy the service and confirm the build/start commands complete.
2. Open a Render shell and run `python manage.py createsuperuser`; enter credentials interactively.
3. Sign into `/admin/` and set the custom `role` of that account to `ADMIN`. Django staff/superuser flags alone do not grant the TrustVault ADMIN role.
4. Register owner and recipient accounts through `/register/`, then assign recipient role through the authorized user-management page if needed.
5. Upload a test file, grant and revoke access, verify direct URLs, and inspect audit events.

## Storage, static files, and backups

Static assets are collected into `staticfiles/` and served with WhiteNoise when its requirement is installed. Private document storage is not served by WhiteNoise or Django static/media routes. The mounted disk must persist across deploys, be restricted to the service, and be backed up. Back up PostgreSQL and the private disk separately; restoring one without the other can leave document records with missing bytes or unreferenced files.

## Production checks

- Verify `python manage.py check --deploy` after all host-specific environment variables are set.
- Verify HTTPS redirect, secure cookies, allowed hosts, CSRF trusted origins, database TLS, and persistent disk mount.
- Confirm the upload directory is not reachable from a public URL and downloads are authorized attachments.
- Test grant, permission change, revocation, and audit views with separate accounts.
- Do not claim deployment success until these checks are performed against the live service. No live deployment is included or claimed here.
