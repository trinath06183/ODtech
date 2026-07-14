"""
EDMS URL Configuration
======================
All URL patterns for the Enterprise Document Management System.
Namespace: 'edms'
"""

from django.urls import path
from edms import views

app_name = 'edms'

urlpatterns = [

    # ── Dashboard ─────────────────────────────────────────────────────────────
    path('', views.DashboardView.as_view(), name='dashboard'),

    # ── Document List ─────────────────────────────────────────────────────────
    path('documents/', views.DocumentListView.as_view(), name='document_list'),

    # ── Document Upload (2-step wizard) ───────────────────────────────────────
    path('documents/upload/', views.DocumentUploadView.as_view(), name='document_upload'),

    # ── Document Detail ───────────────────────────────────────────────────────
    path('document/<uuid:doc_id>/', views.DocumentDetailView.as_view(), name='document_detail'),

    # ── Document Edit (metadata only) ─────────────────────────────────────────
    path('document/<uuid:doc_id>/edit/', views.DocumentEditView.as_view(), name='document_edit'),

    # ── Document Delete (soft) ────────────────────────────────────────────────
    path('document/<uuid:doc_id>/delete/', views.DocumentDeleteView.as_view(), name='document_delete'),

    # ── Document Restore ──────────────────────────────────────────────────────
    path('document/<uuid:doc_id>/restore/', views.DocumentRestoreView.as_view(), name='document_restore'),

    # ── Document Approve ──────────────────────────────────────────────────────
    path('document/<uuid:doc_id>/approve/', views.DocumentApproveView.as_view(), name='document_approve'),

    # ── Secure Download (latest version) ──────────────────────────────────────
    path('document/<uuid:doc_id>/download/', views.DocumentDownloadView.as_view(), name='document_download'),

    # ── Secure Download (specific version) ───────────────────────────────────
    path(
        'document/<uuid:doc_id>/download/<int:version_number>/',
        views.DocumentDownloadView.as_view(),
        name='document_download_version',
    ),

    # ── In-Browser Preview (latest) ───────────────────────────────────────────
    path('document/<uuid:doc_id>/preview/', views.DocumentPreviewView.as_view(), name='document_preview'),

    # ── In-Browser Preview (specific version) ────────────────────────────────
    path(
        'document/<uuid:doc_id>/preview/<int:version_number>/',
        views.DocumentPreviewView.as_view(),
        name='document_preview_version',
    ),

    # ── Version History ───────────────────────────────────────────────────────
    path('document/<uuid:doc_id>/versions/', views.VersionHistoryView.as_view(), name='version_history'),

    # ── New Version Upload ────────────────────────────────────────────────────
    path(
        'document/<uuid:doc_id>/versions/new/',
        views.NewVersionUploadView.as_view(),
        name='new_version_upload',
    ),

    # ── Search ────────────────────────────────────────────────────────────────
    path('search/', views.SearchView.as_view(), name='search'),
    path('search/save/', views.SaveSearchView.as_view(), name='save_search'),

    # ── Audit Log ─────────────────────────────────────────────────────────────
    path('audit/', views.AuditLogView.as_view(), name='audit_log'),

    # ── Reports ───────────────────────────────────────────────────────────────
    path('reports/', views.ReportsView.as_view(), name='reports'),

    # ── Download Center ───────────────────────────────────────────────────────
    path('downloads/', views.DownloadCenterView.as_view(), name='download_center'),

    # ── Vendors ───────────────────────────────────────────────────────────────
    path('vendors/', views.VendorListView.as_view(), name='vendor_list'),
    path('vendors/new/', views.VendorCreateView.as_view(), name='vendor_create'),
    path('vendors/<int:vendor_id>/edit/', views.VendorEditView.as_view(), name='vendor_edit'),

    # ── Categories ────────────────────────────────────────────────────────────
    path('categories/', views.CategoryListView.as_view(), name='category_list'),
    path('categories/new/', views.CategoryCreateView.as_view(), name='category_create'),
    path('categories/<int:cat_id>/edit/', views.CategoryEditView.as_view(), name='category_edit'),

    # ── Company Profile ───────────────────────────────────────────────────────
    path('company/', views.CompanyProfileView.as_view(), name='company_profile'),

    # ── Departments ───────────────────────────────────────────────────────────
    path('departments/', views.DepartmentListView.as_view(), name='department_list'),
    path('departments/new/', views.DepartmentCreateView.as_view(), name='department_create'),

    # ── Admin Settings ────────────────────────────────────────────────────────
    path('admin-settings/', views.AdminSettingsView.as_view(), name='admin_settings'),

    # ── Notifications API ─────────────────────────────────────────────────────
    path('api/notifications/', views.NotificationListView.as_view(), name='api_notifications'),
    path(
        'api/notifications/<int:notif_id>/read/',
        views.MarkNotificationReadView.as_view(),
        name='api_notification_read',
    ),
]
