"""
EDMS Models
===========
Complete database schema for the Enterprise Document Management System.

Models:
  - Department            — Organisational departments
  - EDMSDocumentCategory  — Unlimited document categories
  - EDMSCompanyProfile    — Company-level metadata
  - EDMSVendor            — Vendor master records
  - EDMSDocument          — Core document record
  - EDMSDocumentVersion   — Immutable version history
  - EDMSDocumentTag       — Tagging system
  - EDMSDocumentAccess    — Per-user/role access grants
  - EDMSAuditLog          — Complete audit trail
  - EDMSDocumentDownload  — Download event records
  - EDMSNotification      — In-app notification inbox
  - EDMSSavedSearch       — Saved filter presets

Design decisions:
  • Files are NEVER overwritten — every upload creates a new version.
  • Direct file URLs are NEVER exposed — all access is through Django views.
  • SHA-256 checksums prevent duplicates and verify integrity.
  • All timestamps are timezone-aware.
  • Searchable fields are indexed for performance.
"""

import os
import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from core.models import TimeStampedModel

User = get_user_model()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _edms_upload_path(instance, filename):
    """
    Store uploaded files in a private directory keyed by document UUID and
    version number.  The path is:
        edms_storage/<category_slug>/<doc_uuid>/v<version>/<safe_filename>
    This path is NEVER exposed directly in HTTP responses.
    """
    ext = os.path.splitext(filename)[1].lower()
    safe_name = slugify(os.path.splitext(filename)[0])[:60] + ext
    category_slug = slugify(instance.document.category.name) if instance.document.category else 'uncategorized'
    return os.path.join(
        'edms_storage',
        category_slug,
        str(instance.document.id),
        f'v{instance.version_number}',
        safe_name,
    )


# ─── Department ───────────────────────────────────────────────────────────────

class Department(TimeStampedModel):
    """Organisational department master."""
    name        = models.CharField(max_length=100, unique=True, db_index=True)
    code        = models.CharField(max_length=20, unique=True, blank=True)
    description = models.TextField(blank=True)
    head        = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='headed_departments',
    )
    is_active   = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name        = 'Department'
        verbose_name_plural = 'Departments'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = slugify(self.name).upper()[:20]
        super().save(*args, **kwargs)


# ─── Document Category ────────────────────────────────────────────────────────

class EDMSDocumentCategory(TimeStampedModel):
    """Unlimited, user-managed document categories with preset defaults."""

    DEFAULT_CATEGORIES = [
        'Company Registration', 'GST', 'PAN', 'Udyam', 'MSME',
        'ISO Certificates', 'Company Logo', 'Company Seal',
        'Digital Signature', 'Letterhead', 'Turnover', 'Balance Sheet',
        'Audit Report', 'Experience Certificate', 'Past Performance',
        'Purchase Order', 'Purchase Invoice', 'Vendor Invoice', 'Bills',
        'Payment Proof', 'Agreements', 'Legal Documents', 'HR Documents',
        'Project Documents', 'Tender Documents', 'Other',
    ]

    name        = models.CharField(max_length=150, unique=True, db_index=True)
    slug        = models.SlugField(max_length=160, unique=True, blank=True)
    description = models.TextField(blank=True)
    icon        = models.CharField(max_length=50, default='📄', blank=True)
    color       = models.CharField(max_length=20, default='#6366f1', blank=True,
                                   help_text='Hex colour for UI badge')
    parent      = models.ForeignKey(
        'self', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='children',
    )
    is_active   = models.BooleanField(default=True)
    is_default  = models.BooleanField(default=False,
                                      help_text='System-created default category')
    order       = models.PositiveIntegerField(default=0)

    class Meta:
        ordering            = ['order', 'name']
        verbose_name        = 'Document Category'
        verbose_name_plural = 'Document Categories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:160]
        super().save(*args, **kwargs)


# ─── Company Profile ──────────────────────────────────────────────────────────

class EDMSCompanyProfile(TimeStampedModel):
    """Company master record for EDMS metadata stamping."""
    company_name       = models.CharField(max_length=255)
    gst_number         = models.CharField(max_length=20,  blank=True)
    pan_number         = models.CharField(max_length=20,  blank=True)
    cin                = models.CharField(max_length=30,  blank=True, verbose_name='CIN')
    udyam_number       = models.CharField(max_length=30,  blank=True)
    registration_number= models.CharField(max_length=50,  blank=True)
    iso_number         = models.CharField(max_length=50,  blank=True, verbose_name='ISO Number')
    financial_year     = models.CharField(max_length=10,  blank=True, help_text='e.g. 2025-26')
    turnover           = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    address            = models.TextField(blank=True)
    website            = models.URLField(blank=True)
    email              = models.EmailField(blank=True)
    phone              = models.CharField(max_length=20, blank=True)
    logo               = models.ImageField(upload_to='edms_company/', blank=True, null=True)

    class Meta:
        verbose_name        = 'Company Profile'
        verbose_name_plural = 'Company Profiles'

    def __str__(self):
        return self.company_name


# ─── Vendor ───────────────────────────────────────────────────────────────────

class EDMSVendor(TimeStampedModel):
    """Vendor master for linking purchase/invoice documents."""
    name           = models.CharField(max_length=255, db_index=True)
    contact_person = models.CharField(max_length=150, blank=True)
    phone          = models.CharField(max_length=20,  blank=True)
    email          = models.EmailField(blank=True)
    gst_number     = models.CharField(max_length=20,  blank=True, verbose_name='GST')
    pan_number     = models.CharField(max_length=20,  blank=True, verbose_name='PAN')
    address        = models.TextField(blank=True)
    is_active      = models.BooleanField(default=True)

    class Meta:
        ordering            = ['name']
        verbose_name        = 'Vendor'
        verbose_name_plural = 'Vendors'

    def __str__(self):
        return self.name


# ─── Document Tag ─────────────────────────────────────────────────────────────

class EDMSDocumentTag(models.Model):
    """Simple tag for search/filtering documents."""
    name = models.CharField(max_length=80, unique=True, db_index=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:90]
        super().save(*args, **kwargs)


# ─── Document (Core) ──────────────────────────────────────────────────────────

class EDMSDocument(TimeStampedModel):
    """
    Core EDMS document record.
    The actual file is stored in EDMSDocumentVersion to support version control.
    """

    # ── Access Levels ─────────────────────────────────────────────────────────
    ACCESS_PUBLIC          = 'public'
    ACCESS_INTERNAL        = 'internal'
    ACCESS_DEPARTMENT      = 'department'
    ACCESS_MANAGEMENT      = 'management'
    ACCESS_ADMIN           = 'admin'
    ACCESS_LEVEL_CHOICES = (
        (ACCESS_PUBLIC,     'Public'),
        (ACCESS_INTERNAL,   'Internal'),
        (ACCESS_DEPARTMENT, 'Department Only'),
        (ACCESS_MANAGEMENT, 'Management'),
        (ACCESS_ADMIN,      'Admin Only'),
    )

    # ── Approval Status ───────────────────────────────────────────────────────
    APPROVAL_PENDING  = 'pending'
    APPROVAL_APPROVED = 'approved'
    APPROVAL_REJECTED = 'rejected'
    APPROVAL_STATUS_CHOICES = (
        (APPROVAL_PENDING,  'Pending'),
        (APPROVAL_APPROVED, 'Approved'),
        (APPROVAL_REJECTED, 'Rejected'),
    )

    # ── Document Types (within EDMS) ──────────────────────────────────────────
    DOCTYPE_CERTIFICATE  = 'certificate'
    DOCTYPE_LEGAL        = 'legal'
    DOCTYPE_FINANCIAL    = 'financial'
    DOCTYPE_HR           = 'hr'
    DOCTYPE_PURCHASE     = 'purchase'
    DOCTYPE_TENDER       = 'tender'
    DOCTYPE_VENDOR       = 'vendor'
    DOCTYPE_PROJECT      = 'project'
    DOCTYPE_POLICY       = 'policy'
    DOCTYPE_OTHER        = 'other'
    DOCUMENT_TYPE_CHOICES = (
        (DOCTYPE_CERTIFICATE, 'Certificate'),
        (DOCTYPE_LEGAL,       'Legal'),
        (DOCTYPE_FINANCIAL,   'Financial'),
        (DOCTYPE_HR,          'HR'),
        (DOCTYPE_PURCHASE,    'Purchase'),
        (DOCTYPE_TENDER,      'Tender'),
        (DOCTYPE_VENDOR,      'Vendor'),
        (DOCTYPE_PROJECT,     'Project'),
        (DOCTYPE_POLICY,      'Policy/SOP'),
        (DOCTYPE_OTHER,       'Other'),
    )

    # ── Primary Key ───────────────────────────────────────────────────────────
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ── Core Metadata ─────────────────────────────────────────────────────────
    title            = models.CharField(max_length=255, db_index=True)
    description      = models.TextField(blank=True)
    category         = models.ForeignKey(
        EDMSDocumentCategory, on_delete=models.PROTECT,
        related_name='documents',
    )
    department       = models.ForeignKey(
        Department, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='documents',
    )
    document_type    = models.CharField(
        max_length=20, choices=DOCUMENT_TYPE_CHOICES,
        default=DOCTYPE_OTHER, db_index=True,
    )
    keywords         = models.TextField(
        blank=True,
        help_text='Space or comma separated keywords for search',
    )
    reference_number = models.CharField(max_length=100, blank=True, db_index=True)
    tags             = models.ManyToManyField(EDMSDocumentTag, blank=True, related_name='documents')

    # ── Dates ────────────────────────────────────────────────────────────────
    issue_date  = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)

    # ── Ownership & Security ─────────────────────────────────────────────────
    owner        = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='owned_edms_documents',
    )
    uploaded_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='uploaded_edms_documents',
    )
    approved_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='approved_edms_documents',
    )
    approved_at  = models.DateTimeField(null=True, blank=True)

    access_level     = models.CharField(
        max_length=20, choices=ACCESS_LEVEL_CHOICES,
        default=ACCESS_INTERNAL, db_index=True,
    )
    is_confidential  = models.BooleanField(default=False)
    approval_status  = models.CharField(
        max_length=20, choices=APPROVAL_STATUS_CHOICES,
        default=APPROVAL_PENDING, db_index=True,
    )

    # ── Company / Vendor Links ────────────────────────────────────────────────
    company = models.ForeignKey(
        EDMSCompanyProfile, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='documents',
    )
    vendor  = models.ForeignKey(
        EDMSVendor, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='documents',
    )

    # ── Purchase Details ──────────────────────────────────────────────────────
    po_number      = models.CharField(max_length=100, blank=True, verbose_name='PO Number', db_index=True)
    invoice_number = models.CharField(max_length=100, blank=True, db_index=True)
    invoice_date   = models.DateField(null=True, blank=True)
    bill_number    = models.CharField(max_length=100, blank=True)
    amount         = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    tax_amount     = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    currency       = models.CharField(max_length=10, default='INR')
    payment_status = models.CharField(max_length=30, blank=True,
                                      choices=(
                                          ('unpaid', 'Unpaid'),
                                          ('partial', 'Partially Paid'),
                                          ('paid', 'Paid'),
                                      ))

    # ── File Info (cached from latest version) ────────────────────────────────
    current_version  = models.PositiveIntegerField(default=1)
    file_name        = models.CharField(max_length=255, blank=True)
    file_size        = models.PositiveBigIntegerField(null=True, blank=True,
                                                      help_text='Size in bytes')
    mime_type        = models.CharField(max_length=120, blank=True)
    file_extension   = models.CharField(max_length=20, blank=True, db_index=True)
    file_hash        = models.CharField(max_length=64, blank=True, db_index=True,
                                        help_text='SHA-256 hex digest of latest version')

    # ── OCR / AI Future Fields ────────────────────────────────────────────────
    ocr_text         = models.TextField(blank=True,
                                        help_text='OCR-extracted text (future feature)')
    ocr_processed    = models.BooleanField(default=False)

    # ── Commercial Document Link (auto-synced from Documents module) ──────────
    SOURCE_MANUAL     = 'manual'
    SOURCE_COMMERCIAL = 'commercial'
    SOURCE_CHOICES = (
        (SOURCE_MANUAL,     'Manually Uploaded'),
        (SOURCE_COMMERCIAL, 'Auto-synced from Commercial Documents'),
    )
    source_type       = models.CharField(
        max_length=20, choices=SOURCE_CHOICES,
        default=SOURCE_MANUAL, db_index=True,
    )
    commercial_doc    = models.OneToOneField(
        'documents.Document',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='edms_record',
        verbose_name='Commercial Document',
        help_text='Auto-populated when synced from the commercial documents module',
    )

    # ── Soft Delete ───────────────────────────────────────────────────────────
    is_deleted       = models.BooleanField(default=False, db_index=True)
    deleted_at       = models.DateTimeField(null=True, blank=True)
    deleted_by       = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='deleted_edms_documents',
    )
    delete_reason    = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering            = ['-created_at']
        verbose_name        = 'EDMS Document'
        verbose_name_plural = 'EDMS Documents'
        indexes = [
            models.Index(fields=['category', 'is_deleted']),
            models.Index(fields=['department', 'is_deleted']),
            models.Index(fields=['approval_status', 'is_deleted']),
            models.Index(fields=['expiry_date']),
            models.Index(fields=['file_hash']),
        ]

    def __str__(self):
        return f"{self.title} (v{self.current_version})"

    @property
    def latest_version(self):
        """Return the latest EDMSDocumentVersion object."""
        return self.versions.order_by('-version_number').first()

    @property
    def file_size_display(self):
        """Human-readable file size."""
        if not self.file_size:
            return '—'
        for unit in ['B', 'KB', 'MB', 'GB']:
            if self.file_size < 1024:
                return f"{self.file_size:.1f} {unit}"
            self.file_size /= 1024
        return f"{self.file_size:.1f} TB"

    def soft_delete(self, user, reason=''):
        """Mark document as deleted without removing from DB."""
        self.is_deleted    = True
        self.deleted_at    = timezone.now()
        self.deleted_by    = user
        self.delete_reason = reason
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'delete_reason'])

    def restore(self, user):
        """Restore a soft-deleted document."""
        self.is_deleted    = False
        self.deleted_at    = None
        self.deleted_by    = None
        self.delete_reason = ''
        self.save(update_fields=['is_deleted', 'deleted_at', 'deleted_by', 'delete_reason'])

    def approve(self, user):
        """Approve the document."""
        self.approval_status = self.APPROVAL_APPROVED
        self.approved_by     = user
        self.approved_at     = timezone.now()
        self.save(update_fields=['approval_status', 'approved_by', 'approved_at'])

    def is_preview_supported(self):
        """True if in-browser preview is supported for this file type."""
        return self.file_extension in {'.pdf', '.jpg', '.jpeg', '.png',
                                       '.gif', '.bmp', '.webp', '.txt',
                                       '.svg', '.mp4', '.webm'}


# ─── Document Version ─────────────────────────────────────────────────────────

class EDMSDocumentVersion(TimeStampedModel):
    """
    Immutable version record.
    Every upload creates a new version; old files are NEVER overwritten.
    """
    document       = models.ForeignKey(
        EDMSDocument, on_delete=models.CASCADE,
        related_name='versions',
    )
    version_number = models.PositiveIntegerField()
    file           = models.FileField(upload_to=_edms_upload_path,
                                      max_length=500)
    file_name      = models.CharField(max_length=255)
    file_size      = models.PositiveBigIntegerField(help_text='Size in bytes')
    mime_type      = models.CharField(max_length=120)
    file_extension = models.CharField(max_length=20)
    file_hash      = models.CharField(max_length=64, db_index=True,
                                      help_text='SHA-256 hex digest')
    change_note    = models.CharField(max_length=255, blank=True,
                                      help_text='Brief description of changes in this version')
    uploaded_by    = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='uploaded_versions',
    )
    is_current     = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ['-version_number']
        unique_together = [('document', 'version_number')]
        verbose_name        = 'Document Version'
        verbose_name_plural = 'Document Versions'

    def __str__(self):
        return f"{self.document.title} — v{self.version_number}"


# ─── Document Access Grant ────────────────────────────────────────────────────

class EDMSDocumentAccess(TimeStampedModel):
    """
    Per-user / per-role additional access grants beyond the document's
    base access_level.  Used to share documents with specific users
    or temporarily elevate permissions.
    """
    PERMISSION_CHOICES = (
        ('view',            'View'),
        ('preview',         'Preview'),
        ('download',        'Download'),
        ('edit_metadata',   'Edit Metadata'),
        ('delete',          'Delete'),
        ('approve',         'Approve'),
        ('restore',         'Restore'),
        ('share',           'Share'),
        ('export',          'Export'),
    )

    document    = models.ForeignKey(
        EDMSDocument, on_delete=models.CASCADE,
        related_name='access_grants',
    )
    user        = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='edms_access_grants',
    )
    role        = models.CharField(max_length=30, blank=True,
                                   help_text='Role name (if granting to all users of that role)')
    permission  = models.CharField(max_length=20, choices=PERMISSION_CHOICES)
    granted_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True,
        related_name='edms_access_grants_given',
    )
    expires_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Document Access Grant'
        verbose_name_plural = 'Document Access Grants'

    def __str__(self):
        target = self.user or f"Role:{self.role}"
        return f"{target} → {self.permission} on {self.document.title}"

    def is_active(self):
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True


# ─── Audit Log ────────────────────────────────────────────────────────────────

class EDMSAuditLog(models.Model):
    """
    Immutable audit trail.  Every significant action creates one record.
    Records must NEVER be updated or deleted.
    """
    ACTION_LOGIN          = 'login'
    ACTION_LOGOUT         = 'logout'
    ACTION_UPLOAD         = 'upload'
    ACTION_PREVIEW        = 'preview'
    ACTION_DOWNLOAD       = 'download'
    ACTION_DELETE         = 'delete'
    ACTION_RESTORE        = 'restore'
    ACTION_EDIT           = 'edit'
    ACTION_APPROVE        = 'approve'
    ACTION_REJECT         = 'reject'
    ACTION_SHARE          = 'share'
    ACTION_PERM_CHANGE    = 'permission_change'
    ACTION_FAILED_ACCESS  = 'failed_access'
    ACTION_SEARCH         = 'search'
    ACTION_EXPORT         = 'export'
    ACTION_VERSION_CREATE = 'version_create'

    ACTION_CHOICES = (
        (ACTION_LOGIN,          'Login'),
        (ACTION_LOGOUT,         'Logout'),
        (ACTION_UPLOAD,         'Upload'),
        (ACTION_PREVIEW,        'Preview'),
        (ACTION_DOWNLOAD,       'Download'),
        (ACTION_DELETE,         'Delete'),
        (ACTION_RESTORE,        'Restore'),
        (ACTION_EDIT,           'Edit Metadata'),
        (ACTION_APPROVE,        'Approve'),
        (ACTION_REJECT,         'Reject'),
        (ACTION_SHARE,          'Share'),
        (ACTION_PERM_CHANGE,    'Permission Change'),
        (ACTION_FAILED_ACCESS,  'Failed Access'),
        (ACTION_SEARCH,         'Search'),
        (ACTION_EXPORT,         'Export'),
        (ACTION_VERSION_CREATE, 'Version Created'),
    )

    # Who
    user            = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='edms_audit_logs',
    )
    username_cached = models.CharField(max_length=150, blank=True,
                                       help_text='Stored at log time in case user is later deleted')
    user_role       = models.CharField(max_length=30, blank=True)
    department_name = models.CharField(max_length=100, blank=True)

    # What
    action          = models.CharField(max_length=30, choices=ACTION_CHOICES, db_index=True)
    document        = models.ForeignKey(
        EDMSDocument, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='audit_logs',
    )
    document_title  = models.CharField(max_length=255, blank=True,
                                       help_text='Cached at log time')
    description     = models.TextField(blank=True)
    extra_data      = models.JSONField(default=dict, blank=True)

    # Context
    ip_address      = models.GenericIPAddressField(null=True, blank=True)
    user_agent      = models.TextField(blank=True)
    browser         = models.CharField(max_length=100, blank=True)
    operating_system= models.CharField(max_length=100, blank=True)

    # Outcome
    success         = models.BooleanField(default=True)
    failure_reason  = models.CharField(max_length=255, blank=True)

    # When
    timestamp       = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering            = ['-timestamp']
        verbose_name        = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        indexes = [
            models.Index(fields=['action', 'timestamp']),
            models.Index(fields=['user', 'timestamp']),
        ]

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.action} by {self.username_cached}"


# ─── Document Download ────────────────────────────────────────────────────────

class EDMSDocumentDownload(TimeStampedModel):
    """Records every download event for analytics and notifications."""
    document   = models.ForeignKey(
        EDMSDocument, on_delete=models.CASCADE,
        related_name='downloads',
    )
    version    = models.ForeignKey(
        EDMSDocumentVersion, on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    downloaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='edms_downloads',
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    reason     = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Download: {self.document.title} by {self.downloaded_by}"


# ─── In-App Notification ──────────────────────────────────────────────────────

class EDMSNotification(TimeStampedModel):
    """In-app notification record for EDMS events."""
    recipient  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='edms_notifications',
    )
    document   = models.ForeignKey(
        EDMSDocument, on_delete=models.SET_NULL,
        null=True, blank=True,
    )
    title      = models.CharField(max_length=255)
    message    = models.TextField()
    action_url = models.CharField(max_length=255, blank=True)
    is_read    = models.BooleanField(default=False, db_index=True)
    read_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.recipient}] {self.title}"

    def mark_read(self):
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=['is_read', 'read_at'])


# ─── Saved Search ─────────────────────────────────────────────────────────────

class EDMSSavedSearch(TimeStampedModel):
    """User-saved search filter preset."""
    user        = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='edms_saved_searches',
    )
    name        = models.CharField(max_length=100)
    filters     = models.JSONField(default=dict,
                                   help_text='Serialised query-string filters')
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['name']
        unique_together = [('user', 'name')]

    def __str__(self):
        return f"{self.user} — {self.name}"
