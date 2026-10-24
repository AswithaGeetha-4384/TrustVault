from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.AuditedLoginView.as_view(template_name='login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('documents/', views.my_documents_view, name='my_documents'),
    path('documents/shared/', views.shared_documents_view, name='shared_documents'),
    path('documents/recent/', views.recent_documents_view, name='recent_documents'),
    path('documents/starred/', views.starred_documents_view, name='starred_documents'),
    path('documents/trash/', views.trash_view, name='trash_documents'),
    path('activity/', views.activity_view, name='activity'),
    path('folders/create/', views.create_folder_view, name='create_folder'),
    path('folders/<int:pk>/', views.folder_detail_view, name='folder_detail'),
    path('documents/upload/', views.upload_document_view, name='upload_document'),
    path('documents/<int:pk>/', views.document_detail_view, name='document_detail'),
    path('documents/<int:pk>/download/', views.document_download_view, name='document_download'),
    path('documents/<int:pk>/edit/', views.document_edit_view, name='document_edit'),
    path('documents/<int:pk>/rename/', views.rename_document_view, name='rename_document'),
    path('documents/<int:pk>/delete/', views.delete_document_view, name='delete_document'),
    path('documents/<int:pk>/restore/', views.restore_document_view, name='restore_document'),
    path('documents/<int:pk>/star/', views.toggle_star_view, name='toggle_star'),
    path('documents/<int:pk>/permissions/', views.manage_permissions_view, name='manage_permissions'),
    path('documents/<int:pk>/revoke/<int:user_id>/', views.revoke_permission, name='revoke_permission'),
    path('audit/', views.audit_log_view, name='audit_log'),
    path('admin/users/', views.admin_users_view, name='admin_users'),
    path('denied/', views.permission_denied_view, name='permission_denied'),
    path('not-found/', views.custom_404, name='custom_404'),
]
