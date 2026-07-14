"""
EDMS Admin Registration
=======================
Register all EDMS models in the Django admin panel with rich list displays
and filtering for operational management.
"""

from django.contrib import admin
from django.utils.html import format_html

from edms.models import (
    Department,
    EDMSAuditLog,
    EDMSCompanyProfile,
    EDMSDocument,
    EDMSDocumentAccess,
    EDMSDocumentCategory,
    EDMSDocumentDownload,
    EDMSDocumentTag,
    EDMSDocumentVersion,
    EDMSNotification,
    EDMSSavedSearch,
    EDMSVendor,
)


# ─── Department ───────────────────────────────────────────────────────────────

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display  = ('name', 'code', 'head', 'is_active', 'created_at')
    list_filter   = ('is_active',)
    search_fields = ('name', 'code')
    ordering      = ('name',)


# ─── Document Category ────────────────────────────────────────────────────────

@admin.register(EDMSDocumentCategory)
class EDMSDocumentCategoryAdmin(admin.ModelAdmin):
    list_display  = ('name', 'slug', 'parent', 'is_active', 'is_default', 'order')
    list_filter   = ('is_active', 'is_default')
    search_fields = ('name',)
    ordering      = ('order', 'name')
    prepopulated_fields = {'slug': ('name',)}


# ─── Company Profile ──────────────────────────────────────────────────────────

@admin.register(EDMSCompanyProfile)
class EDMSCompanyProfileAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'gst_number', 'pan_number', 'financial_year')


# ─── Vendor ───────────────────────────────────────────────────────────────────

@admin.register(EDMSVendor)
class EDMSVendorAdmin(admin.ModelAdmin):
    list_display  = ('name', 'contact_person', 'phone', 'email', 'gst_number', 'pan_number', 'is_active')
    list_filter   = ('is_active',)
    search_fields = ('name', 'gst_number', 'pan_number', 'email')
    ordering      = ('name',)


# ─── Document Tag ─────────────────────────────────────────────────────────────

@admin.register(EDMSDocumentTag)
class EDMSDocumentTagAdmin(admin.ModelAdmin):
    list_display        = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


# ─── Document Version (inline) ────────────────────────────────────────────────

class EDMSDocumentVersionInline(admin.TabularInline):
    model   = EDMSDocumentVersion
    extra   = 0
    readonly_fields = (
        'version_number', 'file_name', 'file_size', 'mime_type',
        'file_hash', 'uploaded_by', 'is_current', 'created_at',
    )
    can_delete = False


# ─── Document ─────────────────────────────────────────────────────────────────

@admin.register(EDMSDocument)
class EDMSDocumentAdmin(admin.ModelAdmin):
    list_display  = (
        'title', 'category', 'department', 'document_type',
        'approval_status', 'access_level', 'current_version',
        'is_confidential', 'is_deleted', 'created_at',
    )
    list_filter   = (
        'category', 'department', 'document_type',
        'approval_status', 'access_level', 'is_confidential', 'is_deleted',
    )
    search_fields = (
        'title', 'description', 'keywords', 'reference_number',
        'po_number', 'invoice_number', 'file_hash',
    )
    readonly_fields = (
        'id', 'file_hash', 'file_size', 'mime_type',
        'file_extension', 'current_version', 'created_at', 'updated_at',
    )
    filter_horizontal = ('tags',)
    inlines = [EDMSDocumentVersionInline]
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Core Metadata', {
            'fields': (
                'id', 'title', 'description', 'category', 'department',
                'document_type', 'keywords', 'reference_number', 'tags',
            ),
        }),
        ('Dates', {
            'fields': ('issue_date', 'expiry_date'),
        }),
        ('Security & Access', {
            'fields': (
                'owner', 'uploaded_by', 'approved_by', 'approved_at',
                'access_level', 'is_confidential', 'approval_status',
            ),
        }),
        ('Company / Vendor', {
            'fields': ('company', 'vendor'),
            'classes': ('collapse',),
        }),
        ('Purchase Details', {
            'fields': (
                'po_number', 'invoice_number', 'invoice_date',
                'bill_number', 'amount', 'tax_amount', 'currency',
                'payment_status',
            ),
            'classes': ('collapse',),
        }),
        ('File Info (auto-filled)', {
            'fields': (
                'current_version', 'file_name', 'file_size',
                'mime_type', 'file_extension', 'file_hash',
            ),
            'classes': ('collapse',),
        }),
        ('OCR (Future)', {
            'fields': ('ocr_text', 'ocr_processed'),
            'classes': ('collapse',),
        }),
        ('Soft Delete', {
            'fields': ('is_deleted', 'deleted_at', 'deleted_by', 'delete_reason'),
            'classes': ('collapse',),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:  # editing existing object
            return self.readonly_fields + ('uploaded_by',)
        return self.readonly_fields


# ─── Document Version ─────────────────────────────────────────────────────────

@admin.register(EDMSDocumentVersion)
class EDMSDocumentVersionAdmin(admin.ModelAdmin):
    list_display  = (
        'document', 'version_number', 'file_name', 'file_size',
        'mime_type', 'is_current', 'uploaded_by', 'created_at',
    )
    list_filter   = ('is_current', 'mime_type')
    search_fields = ('document__title', 'file_name', 'file_hash')
    readonly_fields = ('file_hash', 'created_at')
    ordering      = ('-created_at',)


# ─── Document Access ──────────────────────────────────────────────────────────

@admin.register(EDMSDocumentAccess)
class EDMSDocumentAccessAdmin(admin.ModelAdmin):
    list_display  = ('document', 'user', 'role', 'permission', 'granted_by', 'expires_at')
    list_filter   = ('permission',)
    search_fields = ('document__title', 'user__username', 'role')


# ─── Audit Log ────────────────────────────────────────────────────────────────

@admin.register(EDMSAuditLog)
class EDMSAuditLogAdmin(admin.ModelAdmin):
    list_display  = (
        'timestamp', 'username_cached', 'user_role',
        'action', 'document_title', 'ip_address', 'browser', 'success',
    )
    list_filter   = ('action', 'success', 'browser')
    search_fields = ('username_cached', 'document_title', 'ip_address', 'description')
    readonly_fields = [f.name for f in EDMSAuditLog._meta.fields]  # all fields readonly
    ordering      = ('-timestamp',)
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False  # Audit logs must never be manually created

    def has_delete_permission(self, request, obj=None):
        return False  # Audit logs must never be deleted

    def has_change_permission(self, request, obj=None):
        return False  # Audit logs must never be modified


# ─── Document Download ────────────────────────────────────────────────────────

@admin.register(EDMSDocumentDownload)
class EDMSDocumentDownloadAdmin(admin.ModelAdmin):
    list_display  = ('document', 'downloaded_by', 'ip_address', 'created_at')
    list_filter   = ()
    search_fields = ('document__title', 'downloaded_by__username', 'ip_address')
    ordering      = ('-created_at',)


# ─── Notification ─────────────────────────────────────────────────────────────

@admin.register(EDMSNotification)
class EDMSNotificationAdmin(admin.ModelAdmin):
    list_display  = ('recipient', 'title', 'is_read', 'created_at')
    list_filter   = ('is_read',)
    search_fields = ('recipient__username', 'title')
    ordering      = ('-created_at',)


# ─── Saved Search ─────────────────────────────────────────────────────────────

@admin.register(EDMSSavedSearch)
class EDMSSavedSearchAdmin(admin.ModelAdmin):
    list_display  = ('user', 'name', 'created_at')
    search_fields = ('user__username', 'name')
    ordering      = ('user', 'name')
