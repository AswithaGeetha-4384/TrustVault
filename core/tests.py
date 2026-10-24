from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AuditEvent, Document, Folder, PermissionGrant, User


class TrustVaultSecurityTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin', email='admin@example.com', password='Strongpass123!', role='ADMIN'
        )
        self.owner = User.objects.create_user(
            username='owner', email='owner@example.com', password='Strongpass123!', role='OWNER'
        )
        self.recipient = User.objects.create_user(
            username='recipient', email='recipient@example.com', password='Strongpass123!', role='RECIPIENT'
        )
        self.other = User.objects.create_user(
            username='other', email='other@example.com', password='Strongpass123!', role='RECIPIENT'
        )

        self.doc = Document.objects.create(
            owner=self.owner,
            title='budget.txt',
            original_filename='budget.txt',
            content='alpha beta gamma\n',
            size=50,
            content_type='text/plain',
        )
        self.doc.file.save('budget.txt', ContentFile(b'alpha beta gamma\n'), save=False)
        self.doc.save(update_fields=['file', 'storage_filename'])

    def tearDown(self):
        for document in Document.objects.all():
            if document.file and document.file.name:
                document.file.delete(save=False)
        super().tearDown()

    def test_unauthenticated_users_cannot_access_protected_document_routes(self):
        response = self.client.get(reverse('document_detail', args=[self.doc.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_owner_can_upload_and_download_document(self):
        self.client.login(username='owner', password='Strongpass123!')
        upload_url = reverse('upload_document')
        file = SimpleUploadedFile('notes.txt', b'hello world', content_type='text/plain')
        response = self.client.post(upload_url, {'title': 'notes.txt', 'file': file})
        self.assertEqual(response.status_code, 302)
        doc = Document.objects.get(title='notes.txt')
        download = self.client.get(reverse('document_download', args=[doc.pk]))
        self.assertEqual(download.status_code, 200)
        self.assertIn(b'hello world', b''.join(download.streaming_content))
        self.assertIn('attachment;', download['Content-Disposition'])
        self.assertEqual(download['Content-Type'], 'application/octet-stream')
        self.assertEqual(download['X-Content-Type-Options'], 'nosniff')
        download.close()

    def test_common_file_types_can_be_uploaded_without_extension_allowlist(self):
        self.client.login(username='owner', password='Strongpass123!')
        samples = [
            ('sample.pdf', b'%PDF-1.7 sample', 'application/pdf'),
            ('sample.docx', b'PK\x03\x04sample', 'application/octet-stream'),
            ('sample.png', b'\x89PNG\r\n\x1a\nsample', 'image/png'),
            ('sample.txt', b'plain text', 'text/plain'),
            ('sample.zip', b'PK\x03\x04sample', 'application/zip'),
            ('sample.unlisted', b'arbitrary bytes\x00', 'application/octet-stream'),
        ]
        for filename, content, content_type in samples:
            with self.subTest(filename=filename):
                response = self.client.post(
                    reverse('upload_document'),
                    {'title': filename, 'file': SimpleUploadedFile(filename, content, content_type=content_type)},
                )
                self.assertEqual(response.status_code, 302)
                document = Document.objects.get(title=filename)
                self.assertEqual(document.original_filename, filename)
                self.assertTrue(document.storage_filename)
                self.assertNotEqual(document.storage_filename, filename)

    def test_oversized_upload_is_rejected_with_clear_error(self):
        from django.test import override_settings

        self.client.login(username='owner', password='Strongpass123!')
        with override_settings(MAX_UPLOAD_SIZE=4):
            response = self.client.post(
                reverse('upload_document'),
                {'title': 'large.txt', 'file': SimpleUploadedFile('large.txt', b'12345', content_type='text/plain')},
            )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'upload limit', status_code=400)

    def test_read_recipient_can_download_shared_document(self):
        self.client.login(username='recipient', password='Strongpass123!')
        PermissionGrant.objects.create(document=self.doc, user=self.recipient, permission='READ')
        response = self.client.get(reverse('document_download', args=[self.doc.pk]))
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_recipient_without_permission_cannot_access_document(self):
        self.client.login(username='recipient', password='Strongpass123!')
        response = self.client.get(reverse('document_detail', args=[self.doc.pk]))
        self.assertEqual(response.status_code, 403)

    def test_user_cannot_access_other_users_document_by_guessing_id(self):
        self.client.login(username='other', password='Strongpass123!')
        response = self.client.get(reverse('document_detail', args=[self.doc.pk]))
        self.assertEqual(response.status_code, 403)

    def test_read_recipient_cannot_edit_document(self):
        PermissionGrant.objects.create(document=self.doc, user=self.recipient, permission='READ')
        self.client.login(username='recipient', password='Strongpass123!')
        response = self.client.post(reverse('document_edit', args=[self.doc.pk]), {'content': 'tampered'})
        self.assertEqual(response.status_code, 403)

    def test_read_recipient_cannot_rename_delete_star_or_reshare(self):
        PermissionGrant.objects.create(document=self.doc, user=self.recipient, permission='READ')
        self.client.login(username='recipient', password='Strongpass123!')
        urls = [
            reverse('rename_document', args=[self.doc.pk]),
            reverse('delete_document', args=[self.doc.pk]),
            reverse('toggle_star', args=[self.doc.pk]),
            reverse('manage_permissions', args=[self.doc.pk]),
            reverse('revoke_permission', args=[self.doc.pk, self.other.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, {'title': 'changed'}).status_code, 403)
        self.assertEqual(self.doc.title, 'budget.txt')
        self.assertIsNone(self.doc.deleted_at)
        self.assertFalse(self.doc.is_starred)

    def test_edit_recipient_can_edit_content_but_cannot_rename_delete_or_reshare(self):
        PermissionGrant.objects.create(document=self.doc, user=self.recipient, permission='EDIT')
        self.client.login(username='recipient', password='Strongpass123!')
        edit_response = self.client.post(reverse('document_edit', args=[self.doc.pk]), {'content': 'updated content'})
        self.assertEqual(edit_response.status_code, 302)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.content, 'updated content')
        self.assertEqual(self.client.post(reverse('rename_document', args=[self.doc.pk]), {'title': 'changed'}).status_code, 403)
        self.assertEqual(self.client.post(reverse('delete_document', args=[self.doc.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('manage_permissions', args=[self.doc.pk])).status_code, 403)

    def test_owner_grants_and_changes_permission_and_recipient_sees_shared_document(self):
        self.client.login(username='owner', password='Strongpass123!')
        manage_url = reverse('manage_permissions', args=[self.doc.pk])
        grant_response = self.client.post(manage_url, {'user': self.recipient.pk, 'permission': 'READ'})
        self.assertEqual(grant_response.status_code, 302)
        self.assertEqual(PermissionGrant.objects.get(document=self.doc, user=self.recipient).permission, 'READ')
        self.assertTrue(AuditEvent.objects.filter(action='PERMISSION_GRANTED', outcome='SUCCESS').exists())

        self.client.post(manage_url, {'user': self.recipient.pk, 'permission': 'EDIT'})
        self.assertEqual(PermissionGrant.objects.get(document=self.doc, user=self.recipient).permission, 'EDIT')
        self.assertTrue(AuditEvent.objects.filter(action='PERMISSION_CHANGED', outcome='SUCCESS').exists())

        self.client.logout()
        self.client.login(username='recipient', password='Strongpass123!')
        shared = self.client.get(reverse('shared_documents'))
        self.assertEqual(shared.status_code, 200)
        self.assertContains(shared, 'budget.txt')

    def test_invalid_and_duplicate_grants_are_handled_without_duplicate_rows(self):
        self.client.login(username='owner', password='Strongpass123!')
        manage_url = reverse('manage_permissions', args=[self.doc.pk])
        invalid = self.client.post(manage_url, {'user': '999999', 'permission': 'READ'})
        self.assertEqual(invalid.status_code, 400)
        self.assertContains(invalid, 'Select a valid choice', status_code=400)

        first = self.client.post(manage_url, {'user': self.recipient.pk, 'permission': 'READ'})
        repeated = self.client.post(manage_url, {'user': self.recipient.pk, 'permission': 'READ'})
        self.assertEqual(first.status_code, 302)
        self.assertEqual(repeated.status_code, 302)
        self.assertEqual(PermissionGrant.objects.filter(document=self.doc, user=self.recipient).count(), 1)

    def test_only_owner_or_admin_can_revoke_and_revocation_denies_old_urls(self):
        grant = PermissionGrant.objects.create(document=self.doc, user=self.recipient, permission='READ')
        revoke_url = reverse('revoke_permission', args=[self.doc.pk, self.recipient.pk])

        self.client.login(username='recipient', password='Strongpass123!')
        self.assertEqual(self.client.post(revoke_url).status_code, 403)
        self.assertTrue(PermissionGrant.objects.filter(pk=grant.pk).exists())

        self.client.logout()
        self.client.login(username='owner', password='Strongpass123!')
        self.assertEqual(self.client.get(revoke_url).status_code, 405)
        self.assertEqual(self.client.post(revoke_url).status_code, 302)
        self.assertFalse(PermissionGrant.objects.filter(pk=grant.pk).exists())
        self.assertTrue(AuditEvent.objects.filter(action='PERMISSION_REVOKED', outcome='SUCCESS').exists())
        self.assertTrue(self.doc.file.storage.exists(self.doc.file.name))

        self.client.logout()
        self.client.login(username='recipient', password='Strongpass123!')
        self.assertEqual(self.client.get(reverse('document_detail', args=[self.doc.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('document_download', args=[self.doc.pk])).status_code, 403)
        self.assertTrue(AuditEvent.objects.filter(action='DENIED_ACCESS', outcome='DENIED').exists())

        self.client.logout()
        self.client.login(username='owner', password='Strongpass123!')
        self.assertEqual(self.client.get(reverse('document_detail', args=[self.doc.pk])).status_code, 200)
        owner_download = self.client.get(reverse('document_download', args=[self.doc.pk]))
        self.assertEqual(owner_download.status_code, 200)
        owner_download.close()

    def test_revocation_requires_csrf_token(self):
        grant = PermissionGrant.objects.create(document=self.doc, user=self.recipient, permission='READ')
        csrf_client = Client(enforce_csrf_checks=True)
        self.assertTrue(csrf_client.login(username='owner', password='Strongpass123!'))
        self.assertEqual(csrf_client.get(reverse('manage_permissions', args=[self.doc.pk])).status_code, 200)
        revoke_url = reverse('revoke_permission', args=[self.doc.pk, self.recipient.pk])
        self.assertEqual(csrf_client.post(revoke_url).status_code, 403)
        self.assertTrue(PermissionGrant.objects.filter(pk=grant.pk).exists())

        csrf_token = csrf_client.cookies['csrftoken'].value
        response = csrf_client.post(revoke_url, HTTP_X_CSRFTOKEN=csrf_token)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PermissionGrant.objects.filter(pk=grant.pk).exists())

    def test_recipient_cannot_grant_access_to_another_user(self):
        PermissionGrant.objects.create(document=self.doc, user=self.recipient, permission='READ')
        self.client.login(username='recipient', password='Strongpass123!')
        response = self.client.post(reverse('manage_permissions', args=[self.doc.pk]), {'user': self.other.pk, 'permission': 'READ'})
        self.assertEqual(response.status_code, 403)

    def test_revoked_recipient_is_denied_on_next_request(self):
        PermissionGrant.objects.create(document=self.doc, user=self.recipient, permission='READ')
        self.client.login(username='recipient', password='Strongpass123!')
        allowed_response = self.client.get(reverse('document_download', args=[self.doc.pk]))
        self.assertEqual(allowed_response.status_code, 200)
        allowed_response.close()
        grant = PermissionGrant.objects.get(document=self.doc, user=self.recipient)
        grant.delete()
        response = self.client.get(reverse('document_download', args=[self.doc.pk]))
        self.assertEqual(response.status_code, 403)

    def test_non_admin_users_cannot_access_global_audit_logs_or_user_management(self):
        self.client.login(username='owner', password='Strongpass123!')
        self.assertEqual(self.client.get(reverse('admin_users')).status_code, 302)
        self.assertEqual(self.client.get(reverse('audit_log')).status_code, 302)

    def test_unlisted_file_extension_is_accepted(self):
        self.client.login(username='owner', password='Strongpass123!')
        arbitrary_file = SimpleUploadedFile('backup.bin', b'arbitrary binary data', content_type='application/octet-stream')
        response = self.client.post(reverse('upload_document'), {'title': 'backup.bin', 'file': arbitrary_file})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Document.objects.filter(original_filename='backup.bin', owner=self.owner).exists())

    def test_audit_integrity_verification_detects_modified_event(self):
        event = AuditEvent.objects.create(action='test', outcome='SUCCESS', details='hello')
        event.hash_value = 'tampered'
        event.save(update_fields=['hash_value'])
        self.assertFalse(AuditEvent.verify_chain())

    def test_unauthorized_attempts_create_audit_events(self):
        self.client.get(reverse('document_detail', args=[self.doc.pk]))
        self.assertTrue(AuditEvent.objects.filter(action='DENIED_ACCESS').exists())

    def test_login_and_logout_work_correctly(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

        response = self.client.post(reverse('login'), {'username': 'owner', 'password': 'Strongpass123!'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertRedirects(response, reverse('dashboard'))

        response = self.client.post(reverse('logout'), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertRedirects(response, reverse('login'))

        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_invalid_login_shows_error_and_does_not_authenticate(self):
        response = self.client.post(reverse('login'), {'username': 'owner', 'password': 'wrong-pass'}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertContains(response, 'username and password did not match')
        self.assertTrue(AuditEvent.objects.filter(action='LOGIN_FAILURE', outcome='DENIED').exists())
        self.client.post(reverse('login'), {'username': 'owner', 'password': 'Strongpass123!'}, follow=True)
        self.assertTrue(AuditEvent.objects.filter(action='LOGIN_SUCCESS', actor=self.owner, outcome='SUCCESS').exists())

    def test_document_views_downloads_uploads_and_denials_are_audited(self):
        self.client.login(username='owner', password='Strongpass123!')
        self.client.get(reverse('document_detail', args=[self.doc.pk]))
        download = self.client.get(reverse('document_download', args=[self.doc.pk]))
        download.close()
        self.client.post(
            reverse('upload_document'),
            {'title': 'audit.txt', 'file': SimpleUploadedFile('audit.txt', b'audit content', content_type='text/plain')},
        )
        self.assertTrue(AuditEvent.objects.filter(action='DOCUMENT_VIEW', target=self.doc.title).exists())
        self.assertTrue(AuditEvent.objects.filter(action='DOCUMENT_DOWNLOAD', target=self.doc.title, outcome='SUCCESS').exists())
        self.assertTrue(AuditEvent.objects.filter(action='DOCUMENT_UPLOAD', outcome='SUCCESS').exists())

        self.client.logout()
        self.client.login(username='other', password='Strongpass123!')
        self.assertEqual(self.client.get(reverse('document_download', args=[self.doc.pk])).status_code, 403)
        self.assertTrue(AuditEvent.objects.filter(action='DENIED_ACCESS', outcome='DENIED').exists())

    def test_registration_creates_custom_user_with_hashed_password(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'newowner',
                'email': 'newowner@example.com',
                'password1': 'Strongpass123!',
                'password2': 'Strongpass123!',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username='newowner')
        self.assertEqual(user.role, User.OWNER)
        self.assertTrue(user.check_password('Strongpass123!'))
        self.assertNotEqual(user.password, 'Strongpass123!')
        self.assertTrue(self.owner.check_password('Strongpass123!'))

    def test_password_validator_failures_show_friendly_messages(self):
        cases = [
            ('commonuser', 'password', 'Your password is too common. Please choose a different password.'),
            ('shortuser', 'tiny', 'Your password is too short. Please use a longer password.'),
            ('numericuser', '8675309123', 'Please choose a password that is not entirely numeric.'),
            ('similaruser', 'similaruser', 'Your password is too similar to your username or other personal information.'),
        ]
        for username, password, expected_message in cases:
            with self.subTest(username=username):
                response = self.client.post(
                    reverse('register'),
                    {
                        'username': username,
                        'email': f'{username}@example.com',
                        'password1': password,
                        'password2': password,
                    },
                )
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, expected_message, status_code=400)
                self.assertFalse(User.objects.filter(username=username).exists())
                self.assertNotContains(response, 'name="password1" value=', status_code=400)
                self.assertNotContains(response, 'name="password2" value=', status_code=400)

    def test_duplicate_email_error_is_not_misreported_as_password_error(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'different-user',
                'email': self.owner.email,
                'password1': 'Strongpass123!',
                'password2': 'Strongpass123!',
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'A user with that email already exists.', status_code=400)
        self.assertNotContains(response, 'password is too common', status_code=400)

    def test_duplicate_registration_is_rejected(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'owner',
                'email': 'owner2@example.com',
                'password1': 'Strongpass123!',
                'password2': 'Strongpass123!',
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'already exists', status_code=400)

    def test_dashboard_requires_authentication(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_logout_control_uses_post_and_csrf(self):
        self.client.login(username='owner', password='Strongpass123!')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'method="post"', count=1)
        self.assertContains(response, 'action="/logout/"', count=1)
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_starred_documents_are_visible_in_starred_view(self):
        self.doc.is_starred = True
        self.doc.save(update_fields=['is_starred'])
        self.client.login(username='owner', password='Strongpass123!')
        response = self.client.get(reverse('starred_documents'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'budget.txt')

    def test_admin_can_open_a_folder_in_the_admin_folder_list(self):
        folder = Folder.objects.create(owner=self.owner, name='Owner folder')
        self.client.login(username='admin', password='Strongpass123!')
        response = self.client.get(reverse('folder_detail', args=[folder.pk]))
        self.assertEqual(response.status_code, 200)

    def test_deleted_documents_are_hidden_from_normal_views(self):
        self.doc.deleted_at = timezone.now()
        self.doc.save(update_fields=['deleted_at'])
        self.client.login(username='owner', password='Strongpass123!')
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'budget.txt')

    def test_search_only_returns_authorized_documents(self):
        self.client.login(username='owner', password='Strongpass123!')
        response = self.client.get(reverse('dashboard'), {'q': 'budget'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'budget.txt')

        self.client.logout()
        self.client.login(username='other', password='Strongpass123!')
        response = self.client.get(reverse('dashboard'), {'q': 'budget'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'budget.txt')
