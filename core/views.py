from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import SuspiciousFileOperation
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import DocumentEditForm, DocumentRenameForm, DocumentUploadForm, FolderForm, PermissionForm, RegistrationForm
from .models import AuditEvent, Document, Folder, PermissionGrant

User = get_user_model()


class AuditedLoginView(auth_views.LoginView):
    def form_valid(self, form):
        user = form.get_user()
        record_audit(self.request, 'LOGIN_SUCCESS', target=user.username, actor=user)
        return super().form_valid(form)

    def form_invalid(self, form):
        record_audit(
            self.request,
            'LOGIN_FAILURE',
            target=(self.request.POST.get('username') or '')[:255],
            outcome='DENIED',
            details='Authentication failed.',
        )
        return super().form_invalid(form)


def record_audit(request, action, target='', outcome='SUCCESS', details='', actor=None):
    if actor is None:
        actor = request.user if getattr(request, 'user', None) and request.user.is_authenticated else None
    return AuditEvent.objects.create(
        actor=actor,
        action=action,
        target=target,
        outcome=outcome,
        details=details,
        request_path=getattr(request, 'path', '') or '',
        request_method=getattr(request, 'method', '') or '',
    )


def is_admin(user):
    return user.is_authenticated and user.role == User.ADMIN


def can_read_document(user, document):
    if not user or not user.is_authenticated or document.deleted_at is not None:
        return False
    if user.role == User.ADMIN or document.owner == user:
        return True
    return PermissionGrant.objects.filter(document=document, user=user).exists()


def can_edit_document(user, document):
    if not user or not user.is_authenticated or document.deleted_at is not None:
        return False
    if user.role == User.ADMIN or document.owner == user:
        return True
    grant = PermissionGrant.objects.filter(document=document, user=user).first()
    return grant is not None and grant.permission == PermissionGrant.EDIT


def can_manage_permissions(user, document):
    return user.is_authenticated and (user.role == User.ADMIN or document.owner == user)


def visible_documents_for_user(user, include_deleted=False):
    if not user or not user.is_authenticated:
        return Document.objects.none()
    if user.role == User.ADMIN:
        qs = Document.objects.all()
    else:
        qs = Document.objects.filter(Q(owner=user) | Q(permissions__user=user)).distinct()
    if not include_deleted:
        qs = qs.filter(deleted_at__isnull=True)
    return qs.select_related('owner', 'parent_folder').prefetch_related('permissions')


def accessible_folders_for_user(user):
    if not user or not user.is_authenticated:
        return Folder.objects.none()
    if user.role == User.ADMIN:
        return Folder.objects.all()
    return Folder.objects.filter(owner=user)


def home_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return redirect('login')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, 'Account created. Please sign in.')
            return redirect('login')
        return render(request, 'register.html', {'form': form}, status=400)

    return render(request, 'register.html', {'form': RegistrationForm()})


@login_required
def dashboard_view(request):
    user = request.user
    query = request.GET.get('q', '').strip()
    documents = visible_documents_for_user(user).order_by('-updated_at')
    if query:
        documents = documents.filter(Q(title__icontains=query) | Q(original_filename__icontains=query))

    folders = accessible_folders_for_user(user)
    owned_count = Document.objects.filter(owner=user, deleted_at__isnull=True).count()
    shared_count = Document.objects.filter(permissions__user=user, deleted_at__isnull=True).exclude(owner=user).distinct().count()
    starred_count = Document.objects.filter(Q(owner=user) | Q(permissions__user=user), is_starred=True, deleted_at__isnull=True).distinct().count()
    activity = AuditEvent.objects.filter(actor=user).order_by('-created_at')[:10]
    return render(request, 'dashboard.html', {
        'documents': documents,
        'folders': folders,
        'owned_count': owned_count,
        'shared_count': shared_count,
        'starred_count': starred_count,
        'query': query,
        'activity': activity,
        'page_title': 'My Drive',
    })


@login_required
def my_documents_view(request):
    documents = Document.objects.filter(owner=request.user, deleted_at__isnull=True)
    folders = Folder.objects.filter(owner=request.user)
    return render(request, 'document_list.html', {'documents': documents, 'folders': folders, 'page_title': 'My Drive'})


@login_required
def shared_documents_view(request):
    documents = Document.objects.filter(permissions__user=request.user, deleted_at__isnull=True).exclude(owner=request.user).distinct()
    return render(request, 'document_list.html', {'documents': documents, 'page_title': 'Shared with me'})


@login_required
def recent_documents_view(request):
    documents = visible_documents_for_user(request.user).order_by('-updated_at')[:20]
    return render(request, 'document_list.html', {'documents': documents, 'page_title': 'Recent'})


@login_required
def starred_documents_view(request):
    documents = visible_documents_for_user(request.user).filter(is_starred=True)
    return render(request, 'document_list.html', {'documents': documents, 'page_title': 'Starred'})


@login_required
def trash_view(request):
    if request.user.role == User.ADMIN:
        documents = Document.objects.filter(deleted_at__isnull=False)
    else:
        documents = Document.objects.filter(owner=request.user, deleted_at__isnull=False)
    return render(request, 'document_list.html', {'documents': documents, 'page_title': 'Trash'})


@login_required
def activity_view(request):
    events = AuditEvent.objects.filter(actor=request.user).order_by('-created_at')[:25]
    return render(request, 'audit_log.html', {'events': events, 'chain_ok': AuditEvent.verify_chain(), 'page_title': 'Activity'})


@login_required
def create_folder_view(request):
    if request.user.role not in {User.OWNER, User.ADMIN}:
        record_audit(request, 'DENIED_ACCESS', target='folder_create', outcome='DENIED', details='Recipient attempted to create folder.')
        return HttpResponseForbidden(render(request, 'error_page.html', {'message': 'Only owners and admins may create folders.'}, status=403))

    if request.method == 'POST':
        form = FolderForm(request.POST, owner=request.user)
        if form.is_valid():
            folder = form.save(commit=False)
            folder.owner = request.user
            folder.save()
            record_audit(request, 'FOLDER_CREATED', target=folder.name, outcome='SUCCESS', details='Folder created.')
            messages.success(request, 'Folder created successfully.')
            return redirect('dashboard')
        return render(request, 'folder_form.html', {'form': form}, status=400)

    form = FolderForm(owner=request.user)
    return render(request, 'folder_form.html', {'form': form})


@login_required
def folder_detail_view(request, pk):
    folders = Folder.objects.all() if is_admin(request.user) else Folder.objects.filter(owner=request.user)
    folder = get_object_or_404(folders, pk=pk)
    documents = visible_documents_for_user(request.user).filter(parent_folder=folder)
    return render(request, 'document_list.html', {'documents': documents, 'folder': folder, 'page_title': folder.name})


@login_required
def upload_document_view(request):
    if not (request.user.role in {User.OWNER, User.ADMIN}):
        record_audit(request, 'DENIED_ACCESS', target='upload_document', outcome='DENIED', details='Recipient attempted to upload document.')
        return HttpResponseForbidden(render(request, 'error_page.html', {'message': 'Only document owners may upload files.'}, status=403))

    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES, owner=request.user)
        if form.is_valid():
            uploaded = request.FILES['file']
            document = form.save(commit=False)
            document.owner = request.user
            document.original_filename = Path(uploaded.name).name
            document.size = getattr(uploaded, 'size', 0)
            document.content_type = getattr(uploaded, 'content_type', 'text/plain') or 'text/plain'
            document.title = form.cleaned_data['title']
            document.parent_folder = form.cleaned_data.get('parent_folder')
            if uploaded.name.lower().endswith('.txt'):
                try:
                    document.content = uploaded.read().decode('utf-8')
                except UnicodeDecodeError:
                    document.content = uploaded.read().decode('utf-8', errors='replace')
                uploaded.seek(0)

            suffix = Path(document.original_filename).suffix
            if not suffix[1:].isascii() or not suffix[1:].isalnum() or len(suffix) > 21:
                suffix = ''
            storage_name = f'{uuid4().hex}{suffix.lower()}'
            document.storage_filename = storage_name
            try:
                document.file.save(storage_name, uploaded, save=False)
                document.save()
            except (OSError, ValueError, SuspiciousFileOperation):
                if document.file and document.file.name:
                    document.file.storage.delete(document.file.name)
                form.add_error('file', 'The file could not be saved. Please try again.')
                record_audit(request, 'DOCUMENT_UPLOAD', target='upload', outcome='FAILURE', details='File storage failed.')
                return render(request, 'document_form.html', {'form': form}, status=400)
            record_audit(request, 'DOCUMENT_UPLOAD', target=document.title, outcome='SUCCESS', details=f'Uploaded {document.original_filename}')
            messages.success(request, 'Document uploaded successfully.')
            return redirect('document_detail', pk=document.pk)
        record_audit(request, 'DOCUMENT_UPLOAD', target='upload', outcome='DENIED', details='Upload validation failed.')
        return render(request, 'document_form.html', {'form': form}, status=400)

    form = DocumentUploadForm(owner=request.user)
    return render(request, 'document_form.html', {'form': form})


@login_required
def document_detail_view(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if not can_read_document(request.user, document):
        record_audit(request, 'DENIED_ACCESS', target=document.title, outcome='DENIED', details='User not allowed to view document.')
        return HttpResponseForbidden(render(request, 'error_page.html', {'message': 'You do not have permission to view this document.'}, status=403))

    document.last_accessed_at = timezone.now()
    document.save(update_fields=['last_accessed_at', 'updated_at'])
    permission_grant = PermissionGrant.objects.filter(document=document, user=request.user).first()
    record_audit(request, 'DOCUMENT_VIEW', target=document.title, outcome='SUCCESS', details='Document viewed by authorized user.')
    return render(request, 'document_detail.html', {'document': document, 'permission': permission_grant})


@login_required
def document_download_view(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if not can_read_document(request.user, document):
        record_audit(request, 'DENIED_ACCESS', target=document.title, outcome='DENIED', details='User not allowed to download document.')
        return HttpResponseForbidden(render(request, 'error_page.html', {'message': 'Access denied.'}, status=403))
    try:
        if not document.file or not document.file.name:
            raise FileNotFoundError
        file_handle = document.file.open('rb')
    except (FileNotFoundError, ValueError):
        record_audit(request, 'DOCUMENT_DOWNLOAD', target=document.title, outcome='DENIED', details='Missing file on disk.')
        raise Http404('Document file is missing.')

    document.last_accessed_at = timezone.now()
    document.save(update_fields=['last_accessed_at', 'updated_at'])
    response = FileResponse(file_handle, as_attachment=True, filename=document.original_filename or document.title)
    response['Content-Type'] = 'application/octet-stream'
    response['X-Content-Type-Options'] = 'nosniff'
    record_audit(request, 'DOCUMENT_DOWNLOAD', target=document.title, outcome='SUCCESS', details='Document downloaded by authorized user.')
    return response


@login_required
def document_edit_view(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if not can_edit_document(request.user, document):
        record_audit(request, 'DENIED_ACCESS', target=document.title, outcome='DENIED', details='User lacks edit permission.')
        return HttpResponseForbidden(render(request, 'error_page.html', {'message': 'You do not have edit permission.'}, status=403))

    if request.method == 'POST':
        form = DocumentEditForm(request.POST)
        if form.is_valid():
            document.content = form.cleaned_data['content']
            document.updated_at = timezone.now()
            document.save(update_fields=['content', 'updated_at'])
            record_audit(request, 'DOCUMENT_EDIT', target=document.title, outcome='SUCCESS', details='Document content updated.')
            messages.success(request, 'Document updated.')
            return redirect('document_detail', pk=document.pk)
        return render(request, 'document_edit.html', {'form': form, 'document': document}, status=400)

    form = DocumentEditForm(initial={'content': document.content})
    return render(request, 'document_edit.html', {'form': form, 'document': document})


@login_required
@require_http_methods(['POST'])
def rename_document_view(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if not (request.user == document.owner or is_admin(request.user)):
        record_audit(request, 'DENIED_ACCESS', target=document.title, outcome='DENIED', details='User attempted to rename document without ownership.')
        return HttpResponseForbidden(render(request, 'error_page.html', {'message': 'Only the owner may rename this document.'}, status=403))

    form = DocumentRenameForm(request.POST, instance=document)
    if form.is_valid():
        document.title = form.cleaned_data['title']
        document.save(update_fields=['title', 'updated_at'])
        record_audit(request, 'DOCUMENT_RENAME', target=document.title, outcome='SUCCESS', details='Document renamed.')
        messages.success(request, 'Document renamed successfully.')
        return redirect('document_detail', pk=document.pk)
    messages.error(request, 'Could not rename document.')
    return redirect('document_detail', pk=document.pk)


@login_required
@require_http_methods(['POST'])
def toggle_star_view(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if not (request.user == document.owner or is_admin(request.user)):
        record_audit(request, 'DENIED_ACCESS', target=document.title, outcome='DENIED', details='User attempted to star without access.')
        return HttpResponseForbidden(render(request, 'error_page.html', {'message': 'Access denied.'}, status=403))

    document.is_starred = not document.is_starred
    document.save(update_fields=['is_starred', 'updated_at'])
    record_audit(request, 'DOCUMENT_STARRED', target=document.title, outcome='SUCCESS', details=f'{document.title} starred status changed.')
    messages.success(request, 'Document starred state updated.')
    return redirect('document_detail', pk=document.pk)


@login_required
@require_http_methods(['POST'])
def delete_document_view(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if not (request.user == document.owner or is_admin(request.user)):
        record_audit(request, 'DENIED_ACCESS', target=document.title, outcome='DENIED', details='User attempted to delete document without ownership.')
        return HttpResponseForbidden(render(request, 'error_page.html', {'message': 'Only the owner may delete this document.'}, status=403))

    document.deleted_at = timezone.now()
    document.save(update_fields=['deleted_at', 'updated_at'])
    record_audit(request, 'DOCUMENT_DELETE', target=document.title, outcome='SUCCESS', details='Document moved to trash.')
    messages.success(request, 'Document moved to trash.')
    return redirect('dashboard')


@login_required
@require_http_methods(['POST'])
def restore_document_view(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if not (request.user == document.owner or is_admin(request.user)):
        record_audit(request, 'DENIED_ACCESS', target=document.title, outcome='DENIED', details='User attempted to restore without ownership.')
        return HttpResponseForbidden(render(request, 'error_page.html', {'message': 'Only the owner may restore this document.'}, status=403))

    document.deleted_at = None
    document.save(update_fields=['deleted_at', 'updated_at'])
    record_audit(request, 'DOCUMENT_RESTORE', target=document.title, outcome='SUCCESS', details='Document restored from trash.')
    messages.success(request, 'Document restored successfully.')
    return redirect('trash_documents')


@login_required
def manage_permissions_view(request, pk):
    document = get_object_or_404(Document, pk=pk)
    if not can_manage_permissions(request.user, document):
        record_audit(request, 'DENIED_ACCESS', target=document.title, outcome='DENIED', details='User attempted to manage permissions without ownership.')
        return HttpResponseForbidden(render(request, 'error_page.html', {'message': 'Only the document owner can manage permissions.'}, status=403))

    users = User.objects.exclude(pk=request.user.pk)
    form = PermissionForm(available_users=users)

    if request.method == 'POST':
        form = PermissionForm(request.POST, available_users=users)
        if form.is_valid():
            target_user = form.cleaned_data['user']
            permission_value = form.cleaned_data['permission']
            if target_user == document.owner:
                messages.error(request, 'You cannot grant permissions to the owner.')
                return render(request, 'permissions.html', {'document': document, 'form': form, 'grants': document.permissions.all()})
            grant = PermissionGrant.objects.filter(document=document, user=target_user).first()
            if grant is None:
                PermissionGrant.objects.create(document=document, user=target_user, permission=permission_value)
                action = 'PERMISSION_GRANTED'
                messages.success(request, f'{permission_value} access granted to {target_user.username}.')
            elif grant.permission != permission_value:
                old_permission = grant.permission
                grant.permission = permission_value
                grant.save(update_fields=['permission'])
                action = 'PERMISSION_CHANGED'
                messages.success(request, f'{target_user.username}\'s access changed from {old_permission} to {permission_value}.')
            else:
                action = 'PERMISSION_CHANGE'
                messages.info(request, f'{target_user.username} already has {permission_value} access.')
            record_audit(request, action, target=document.title, outcome='SUCCESS', details=f'{target_user.username} has {permission_value} access.')
            return redirect('manage_permissions', pk=document.pk)
        record_audit(request, 'PERMISSION_CHANGE', target=document.title, outcome='DENIED', details='Permission form validation failed.')
        return render(request, 'permissions.html', {'document': document, 'form': form, 'grants': document.permissions.all()}, status=400)

    return render(request, 'permissions.html', {'document': document, 'form': form, 'grants': document.permissions.all()})


@login_required
def admin_users_view(request):
    if not is_admin(request.user):
        record_audit(request, 'UNAUTHORIZED_ADMIN', target='user_management', outcome='DENIED', details='Non-admin attempted to access user management.')
        return redirect('dashboard')
    users = User.objects.all()
    if request.method == 'POST':
        for user in users:
            role = request.POST.get(f'role_{user.pk}')
            if role and role in dict(User.ROLE_CHOICES):
                user.role = role
                user.save(update_fields=['role'])
        record_audit(request, 'USER_ROLE_UPDATE', target='user_management', outcome='SUCCESS', details='Administrator updated roles.')
        messages.success(request, 'Role updates saved.')
        return redirect('admin_users')
    return render(request, 'admin_users.html', {'users': users})


@login_required
def audit_log_view(request):
    if not is_admin(request.user):
        record_audit(request, 'UNAUTHORIZED_ADMIN', target='audit_log', outcome='DENIED', details='Non-admin attempted to access audit log.')
        return redirect('dashboard')
    events = AuditEvent.objects.all()[:50]
    chain_ok = AuditEvent.verify_chain()
    return render(request, 'audit_log.html', {'events': events, 'chain_ok': chain_ok})


def permission_denied_view(request, exception=None):
    record_audit(request, 'DENIED_ACCESS', target='request', outcome='DENIED', details='Permission denied for request.')
    return render(request, 'error_page.html', {'message': 'Access denied.'}, status=403)


def custom_404(request, exception=None):
    record_audit(request, 'NOT_FOUND', target='route', outcome='DENIED', details='Resource not found.')
    return render(request, 'error_page.html', {'message': 'Page not found.'}, status=404)


@login_required
@require_http_methods(['POST'])
def revoke_permission(request, pk, user_id):
    document = get_object_or_404(Document, pk=pk)
    if not can_manage_permissions(request.user, document):
        record_audit(request, 'DENIED_ACCESS', target=document.title, outcome='DENIED', details='User attempted to revoke a permission without ownership or admin access.')
        return HttpResponseForbidden('Only the owner can revoke permissions.')
    target = get_object_or_404(User, pk=user_id)
    grant = PermissionGrant.objects.filter(document=document, user=target).first()
    if grant is None:
        record_audit(request, 'PERMISSION_REVOKED', target=document.title, outcome='FAILURE', details=f'No active grant existed for {target.username}.')
        messages.error(request, f'{target.username} has no active grant to revoke.')
        return redirect('manage_permissions', pk=document.pk)
    grant.delete()
    record_audit(request, 'PERMISSION_REVOKED', target=document.title, outcome='SUCCESS', details=f'Revoked access for {target.username}.')
    messages.success(request, 'Access revoked.')
    return redirect('manage_permissions', pk=document.pk)
