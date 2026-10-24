# TrustVault threat model

## Assets

- Uploaded file bytes, original filenames, document metadata, and text content.
- Account credentials, user identities, roles, and active permission grants.
- Audit event rows and their hash-chain values.
- `TRUSTVAULT_SECRET_KEY`, database credentials, and persistent private storage.

## Trust boundaries

- Untrusted browsers and uploaded bytes to the Django application.
- Django application to its configured database.
- Django application to the private filesystem mount.
- Owner/admin operations to recipient access and audit inspection.
- Production reverse proxy to Django, when forwarded HTTPS headers are enabled.

## Attacker capabilities

- Anonymous requests, guessed document IDs, stale URLs, modified form fields, and forged file extensions/content types.
- An authenticated recipient attempting to exceed READ or EDIT grants or preserve access after revocation.
- A compromised owner account acting within that owner's authority.
- A privileged application administrator or database/storage operator.

## Threats and mitigations

### Unauthorized document access

Direct detail, edit, rename, delete, sharing, and download routes check authentication and server-side ownership/grants. Download does not use a public media URL. Grant records are consulted on every request, so revocation applies to old URLs immediately.

### Malicious or active content upload

The server does not restrict by extension, trust browser MIME types, execute uploads, or render them inline. Stored filenames are random and separate from the display filename. Downloads set attachment disposition, `application/octet-stream`, and `nosniff`. This reduces browser execution risk but is not malware scanning or content sanitization.

### Oversized upload and storage exhaustion

The application rejects an individual file above `MAX_UPLOAD_SIZE` (25 MiB by default). This is not a quota system, and request buffering/storage limits should also be configured at the production proxy and host.

### CSRF and unauthorized state changes

Django CSRF middleware is enabled. Logout, upload, edits, sharing, revocation, deletion, restoration, and role updates use POST forms or POST-only routes. Authorization is repeated in the view; hiding a control is not relied upon.

### Credential/session compromise

Passwords are handled by Django authentication and are not written into audit events. Production settings enable secure session/CSRF cookies and HTTPS redirection when debug is off. Deployment must provide a private secret, HTTPS, secure database credentials, and a trusted proxy configuration.

### Audit alteration or repudiation

Audit events record actor where known, action, target, outcome, request path/method, and timestamp. A SHA-256 chain can reveal some row changes, and Django admin exposes events read-only. This is not tamper-proof storage: database administrators can change the rows and recompute hashes. No external append-only service, key-separated signature, or independent log sink is implemented.

## Residual risks and limitations

- No antivirus, content-disarm, extension safety allowlist, per-user quota, rate limiting, MFA, or external immutable audit destination is included.
- The upload limit is checked after Django receives/parses the request; configure proxy/body limits to reduce resource-exhaustion risk.
- Anyone with database administrator access can rewrite application data and audit history. Anyone with private-storage access can read or replace uploaded bytes.
- Application-level admin roles are not a substitute for operating-system, hosting, database, and Django staff-account security.
- SQLite is for local development. Production requires a protected PostgreSQL service and durable private storage.
- No live production deployment has been performed or verified.
