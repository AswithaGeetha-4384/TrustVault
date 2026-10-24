from django.contrib import admin

from .models import AuditEvent, Document, Folder, PermissionGrant, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'role', 'is_staff')
    list_filter = ('role', 'is_staff')
    search_fields = ('username', 'email')


@admin.register(Folder)
class FolderAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'parent', 'created_at')
    search_fields = ('name', 'owner__username')


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'parent_folder', 'created_at', 'size', 'is_starred', 'deleted_at')
    search_fields = ('title', 'owner__username', 'original_filename')


@admin.register(PermissionGrant)
class PermissionGrantAdmin(admin.ModelAdmin):
    list_display = ('document', 'user', 'permission', 'granted_at')
    search_fields = ('document__title', 'user__username')


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ('action', 'outcome', 'actor', 'target', 'created_at')
    list_filter = ('outcome', 'action')
    search_fields = ('target', 'details', 'actor__username')
    readonly_fields = ('actor', 'action', 'target', 'outcome', 'details', 'request_path', 'request_method', 'created_at', 'hash_value')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
