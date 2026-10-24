# Five-minute TrustVault demo

Use a local development instance with separate owner, recipient, and ADMIN accounts. Create accounts through registration; never use a production password in a demo or repository.

| Time | Action | Expected result |
| --- | --- | --- |
| 0:00-0:45 | Sign in as an owner. Upload a small sample file such as a `.txt`, `.pdf`, or `.zip` file. | The detail page shows the original filename. The stored file uses a generated name under private storage. |
| 0:45-1:30 | Open the document detail page and download it. | Download is an attachment. The owner sees a successful upload, view, and download event in their Activity page. |
| 1:30-2:30 | Open Manage permissions. Select the separately registered recipient and grant `READ`. | The owner sees the active grant and a permission-granted event. |
| 2:30-3:15 | Sign in as the recipient in a private browser session. Open “Shared with me”, view the document, and download it. | The document appears and downloads. Rename, delete, star, and sharing actions are unavailable and denied by the server if posted directly. |
| 3:15-4:00 | Sign back in as the owner and change the recipient grant from `READ` to `EDIT`. | The grant changes without creating a duplicate row and the permission-change event is recorded. |
| 4:00-4:40 | Revoke the grant using the POST form. | The grant disappears; the underlying document remains. The revocation event is recorded. |
| 4:40-5:00 | Return to the recipient session and request the old detail and download URLs again. Then sign in as ADMIN and inspect `/audit/`. | Both old URLs return 403 and create denied-access events. ADMIN can inspect the audit chain status. |

For audit inspection, create a Django superuser interactively and set the custom TrustVault `role` to `ADMIN`; Django's superuser flag alone is not the application role. The audit chain is a detection aid, not tamper-proof storage.