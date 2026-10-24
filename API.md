# TrustVault endpoint reference

TrustVault is a server-rendered Django application, not a JSON API. Session authentication is used for protected routes. Django CSRF middleware protects POST requests. A missing document returns 404; a known document without an applicable grant returns 403.

## Routes

| Path | Methods | Authentication and authorization | Behavior |
| --- | --- | --- | --- |
| `/` | GET | Public; authenticated users go to dashboard | Home redirect |
| `/register/` | GET, POST | Public | Creates an OWNER account |
| `/login/` | GET, POST | Public | Login; success/failure are audited |
| `/logout/` | POST | Authenticated | Ends session |
| `/dashboard/` | GET | Authenticated | Shows documents visible to current user |
| `/documents/` | GET | Authenticated | Lists owned documents |
| `/documents/shared/` | GET | Authenticated | Lists documents with a current grant to the user |
| `/documents/recent/` | GET | Authenticated | Lists recent visible documents |
| `/documents/starred/` | GET | Authenticated | Lists starred visible documents |
| `/documents/trash/` | GET | Authenticated; owner sees own, ADMIN sees all | Lists soft-deleted documents |
| `/activity/` | GET | Authenticated | Shows the user's own audit activity |
| `/folders/create/` | GET, POST | OWNER or ADMIN | Creates a folder |
| `/folders/<id>/` | GET | Folder owner | Lists folder contents |
| `/documents/upload/` | GET, POST | OWNER or ADMIN | Uploads any extension within `MAX_UPLOAD_SIZE` |
| `/documents/<id>/` | GET | Owner, ADMIN, or current READ/EDIT grant | Displays document metadata and records a view |
| `/documents/<id>/download/` | GET | Owner, ADMIN, or current READ/EDIT grant | Private attachment download; response is `application/octet-stream` |
| `/documents/<id>/edit/` | GET, POST | Owner, ADMIN, or EDIT grant | Edits the document's text-content field only |
| `/documents/<id>/rename/` | POST | Owner or ADMIN | Renames the document title |
| `/documents/<id>/delete/` | POST | Owner or ADMIN | Moves document to trash; underlying file remains |
| `/documents/<id>/restore/` | POST | Owner or ADMIN | Restores a trashed document |
| `/documents/<id>/star/` | POST | Owner or ADMIN | Changes starred state |
| `/documents/<id>/permissions/` | GET, POST | Owner or ADMIN | Grants or changes READ/EDIT access |
| `/documents/<id>/revoke/<user_id>/` | POST only | Owner or ADMIN | Deletes a grant; next request checks current grants |
| `/audit/` | GET | Custom ADMIN role | Shows latest audit records and chain verification status |
| `/admin/users/` | GET, POST | Custom ADMIN role | Changes application roles |
| `/admin/` | Django admin methods | Django staff/superuser permissions | Django administration; AuditEvent admin is read-only |

## Permission semantics

- OWNER controls their own document and sharing grants.
- ADMIN can read documents and manage grants; role-based TrustVault controls require `role=ADMIN`.
- READ grants allow view and download only.
- EDIT grants also allow editing the current text-content field. They do not allow rename, delete, star changes, or sharing.
- Revocation does not delete the document or stored file.
- Duplicate grants do not create extra rows; selecting the existing permission reports that it already exists. Selecting a different permission changes the grant.

## Download and audit responses

Authorized downloads return 200 with attachment disposition and `nosniff`. A denied request returns 403 and records a denied-access event. Missing storage bytes return 404 and record a failed download event. Audit rows contain timestamps, actor where known, action, target, outcome, and request metadata; passwords and file contents are not logged.
