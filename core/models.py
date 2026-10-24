import hashlib
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from .storage import PrivateFileSystemStorage


class User(AbstractUser):
    ADMIN = 'ADMIN'
    OWNER = 'OWNER'
    RECIPIENT = 'RECIPIENT'
    ROLE_CHOICES = [
        (ADMIN, 'Admin'),
        (OWNER, 'Document Owner'),
        (RECIPIENT, 'Recipient'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=RECIPIENT)

    def is_admin(self):
        return self.role == self.ADMIN

    def is_owner(self):
        return self.role == self.OWNER

    def is_recipient(self):
        return self.role == self.RECIPIENT


class Folder(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='folders')
    name = models.CharField(max_length=200)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def breadcrumb(self):
        parts = []
        current = self
        while current is not None:
            parts.append(current.name)
            current = current.parent
        return list(reversed(parts))


class Document(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_documents')
    title = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255, blank=True)
    storage_filename = models.CharField(max_length=255, unique=True, blank=True)
    file = models.FileField(upload_to='documents/', storage=PrivateFileSystemStorage(), blank=True, null=True)
    content = models.TextField(blank=True)
    content_type = models.CharField(max_length=100, default='text/plain')
    size = models.BigIntegerField(default=0)
    parent_folder = models.ForeignKey(Folder, on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    is_starred = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    @property
    def is_shared(self):
        return self.permissions.exists()

    @property
    def display_type(self):
        name = (self.original_filename or self.title).lower()
        if name.endswith('.pdf'):
            return 'PDF'
        if name.endswith('.txt'):
            return 'TXT'
        return 'FILE'

    @property
    def file_icon(self):
        extension = self.display_type
        if extension == 'PDF':
            return '📄'
        if extension == 'TXT':
            return '📝'
        return '📁'

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.storage_filename and self.original_filename:
            name = Path(self.original_filename).stem or 'document'
            suffix = Path(self.original_filename).suffix or '.txt'
            safe_name = ''.join(ch for ch in name if ch.isalnum() or ch in {'-', '_'}) or 'document'
            self.storage_filename = f'{safe_name}-{timezone.now().strftime("%Y%m%d%H%M%S%f")}{suffix}'
            if self.file and not self.file.name:
                self.file.name = self.storage_filename
        elif not self.storage_filename and self.file and self.file.name:
            self.storage_filename = Path(self.file.name).name
        super().save(*args, **kwargs)


class PermissionGrant(models.Model):
    READ = 'READ'
    EDIT = 'EDIT'
    PERMISSION_CHOICES = [
        (READ, 'Read'),
        (EDIT, 'Edit'),
    ]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='permissions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='granted_permissions')
    permission = models.CharField(max_length=10, choices=PERMISSION_CHOICES)
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('document', 'user')
        indexes = [models.Index(fields=['document', 'user'])]


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_events')
    action = models.CharField(max_length=100)
    target = models.CharField(max_length=255, blank=True)
    outcome = models.CharField(max_length=20, default='SUCCESS')
    details = models.TextField(blank=True)
    request_path = models.CharField(max_length=255, blank=True)
    request_method = models.CharField(max_length=10, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    hash_value = models.CharField(max_length=128, blank=True, editable=False)

    class Meta:
        ordering = ['-created_at']

    def payload(self, previous_hash=''):
        return (
            f"{self.created_at.isoformat()}{self.action}{self.target}{self.outcome}{self.details}"
            f"{self.request_path}{self.request_method}{previous_hash}"
        )

    def save(self, *args, **kwargs):
        if self.created_at is None:
            self.created_at = timezone.now()
        if not self.hash_value:
            previous_hash = None
            latest = AuditEvent.objects.order_by('-id').first()
            if latest:
                previous_hash = latest.hash_value
            payload = self.payload(previous_hash or '')
            self.hash_value = hashlib.sha256(((previous_hash or '') + payload).encode('utf-8')).hexdigest()
        super().save(*args, **kwargs)

    @classmethod
    def compute_hash(cls, previous_hash, record):
        payload = (
            f"{record.created_at.isoformat()}{record.action}{record.target}{record.outcome}{record.details}"
            f"{record.request_path}{record.request_method}{previous_hash or ''}"
        )
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    @classmethod
    def verify_chain(cls):
        records = list(cls.objects.order_by('id'))
        previous_hash = ''
        for record in records:
            expected = cls.compute_hash(previous_hash, record)
            if record.hash_value != expected:
                return False
            previous_hash = record.hash_value
        return True

    def __str__(self):
        return f'{self.action} - {self.outcome}'
