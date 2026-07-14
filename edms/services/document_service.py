"""
DocumentService  |  SearchService  |  VersionService
=====================================================
High-level business logic for document operations.
Views MUST call services; never put business logic in views.
"""

import logging
from django.db import transaction
from django.db.models import Q, Count, Sum
from django.utils import timezone

logger = logging.getLogger('edms.services')


# ─── DocumentService ──────────────────────────────────────────────────────────

class DocumentService:
    """CRUD and lifecycle operations for EDMSDocument."""

    @staticmethod
    @transaction.atomic
    def create_document(validated_data, uploaded_file, user, request=None):
        """
        Create a new EDMSDocument + first version.

        Args:
            validated_data (dict): Cleaned data from DocumentUploadForm.
            uploaded_file:         InMemoryUploadedFile or TemporaryUploadedFile.
            user:                  The uploading User.
            request:               HttpRequest for audit context.

        Returns:
            (EDMSDocument, EDMSDocumentVersion)
        """
        from edms.models import EDMSDocument, EDMSDocumentTag
        from edms.services.upload_service import UploadService
        from edms.services.audit_service import AuditService
        from edms.services.notification_service import NotificationService

        tags_data = validated_data.pop('tags', [])

        document = EDMSDocument(
            owner=user,
            uploaded_by=user,
            **validated_data,
        )
        document.save()

        # Attach tags
        if tags_data:
            document.tags.set(tags_data)

        # Create first version
        version = UploadService.create_version(
            document=document,
            uploaded_file=uploaded_file,
            uploaded_by=user,
            change_note='Initial upload',
        )

        # Audit log
        AuditService.log(
            action='upload',
            request=request,
            user=user,
            document=document,
            description=f"Document '{document.title}' uploaded (v1)",
        )

        # Notify approvers
        try:
            NotificationService.notify_approvers(document, request)
        except Exception as exc:
            logger.warning("[EDMS] Approval notification failed: %s", exc)

        logger.info("[EDMS] Document created: %s (id=%s)", document.title, document.id)
        return document, version

    @staticmethod
    @transaction.atomic
    def update_metadata(document, validated_data, user, request=None):
        """Update editable metadata fields (NOT the file itself)."""
        from edms.services.audit_service import AuditService

        tags_data = validated_data.pop('tags', None)
        for field, value in validated_data.items():
            setattr(document, field, value)
        document.save()

        if tags_data is not None:
            document.tags.set(tags_data)

        AuditService.log(
            action='edit',
            request=request,
            user=user,
            document=document,
            description=f"Metadata updated for '{document.title}'",
        )
        return document

    @staticmethod
    @transaction.atomic
    def upload_new_version(document, uploaded_file, user, change_note='', request=None):
        """Upload a new version of an existing document."""
        from edms.services.upload_service import UploadService
        from edms.services.audit_service import AuditService
        from edms.services.notification_service import NotificationService

        version = UploadService.create_version(
            document=document,
            uploaded_file=uploaded_file,
            uploaded_by=user,
            change_note=change_note or f"Version {document.current_version + 1}",
        )

        AuditService.log(
            action='version_create',
            request=request,
            user=user,
            document=document,
            description=f"New version v{version.version_number} uploaded for '{document.title}'",
        )

        try:
            NotificationService.notify_md(
                event_type='modify',
                document=document,
                actor_request=request,
                reason=change_note,
            )
        except Exception as exc:
            logger.warning("[EDMS] Modify notification failed: %s", exc)

        return document, version

    @staticmethod
    def soft_delete(document, user, reason='', request=None):
        """Soft-delete a document."""
        from edms.services.audit_service import AuditService
        from edms.services.notification_service import NotificationService

        document.soft_delete(user=user, reason=reason)

        AuditService.log(
            action='delete',
            request=request,
            user=user,
            document=document,
            description=f"Document '{document.title}' deleted. Reason: {reason}",
        )

        try:
            NotificationService.notify_md(
                event_type='delete',
                document=document,
                actor_request=request,
                reason=reason,
            )
        except Exception as exc:
            logger.warning("[EDMS] Delete notification failed: %s", exc)

    @staticmethod
    def restore(document, user, request=None):
        """Restore a soft-deleted document."""
        from edms.services.audit_service import AuditService

        document.restore(user=user)
        AuditService.log(
            action='restore',
            request=request,
            user=user,
            document=document,
            description=f"Document '{document.title}' restored.",
        )

    @staticmethod
    def approve(document, user, request=None):
        """Approve a pending document."""
        from edms.services.audit_service import AuditService
        from edms.services.notification_service import NotificationService

        document.approve(user=user)
        AuditService.log(
            action='approve',
            request=request,
            user=user,
            document=document,
            description=f"Document '{document.title}' approved.",
        )
        # Notify the uploader
        try:
            NotificationService.notify_user(
                user=document.uploaded_by,
                title=f"Document Approved: {document.title}",
                message=f"Your document '{document.title}' has been approved by {user.get_full_name() or user.username}.",
                document=document,
                action_url=f"/edms/document/{document.id}/",
            )
        except Exception as exc:
            logger.warning("[EDMS] Approve notification failed: %s", exc)

    @staticmethod
    def get_dashboard_stats():
        """Return a dict of statistics for the EDMS dashboard."""
        from edms.models import EDMSDocument, EDMSAuditLog, EDMSDocumentDownload
        from django.utils import timezone
        today = timezone.localdate()

        qs = EDMSDocument.objects.filter(is_deleted=False)
        return {
            'total_documents':      qs.count(),
            'today_uploads':        qs.filter(created_at__date=today).count(),
            'today_downloads':      EDMSDocumentDownload.objects.filter(created_at__date=today).count(),
            'pending_approvals':    qs.filter(approval_status='pending').count(),
            'expiring_soon':        qs.filter(
                expiry_date__gte=today,
                expiry_date__lte=today + timezone.timedelta(days=30),
            ).count(),
            'expired':              qs.filter(expiry_date__lt=today).count(),
            'by_category':          list(
                qs.values('category__name').annotate(count=Count('id')).order_by('-count')[:10]
            ),
            'by_department':        list(
                qs.values('department__name').annotate(count=Count('id')).order_by('-count')[:10]
            ),
            'most_downloaded':      list(
                qs.annotate(dl_count=Count('downloads')).order_by('-dl_count')[:5]
            ),
            'recent_activities':    list(
                EDMSAuditLog.objects.select_related('user', 'document')
                .order_by('-timestamp')[:10]
            ),
            'recently_uploaded':    list(
                qs.select_related('category', 'owner').order_by('-created_at')[:8]
            ),
            'expiring_certificates':list(
                qs.filter(
                    expiry_date__gte=today,
                    expiry_date__lte=today + timezone.timedelta(days=90),
                ).select_related('category').order_by('expiry_date')[:10]
            ),
        }


# ─── SearchService ────────────────────────────────────────────────────────────

class SearchService:
    """Advanced full-text + metadata search for EDMS documents."""

    @staticmethod
    def search(user, filters, base_qs=None):
        """
        Apply all filters and return a queryset.

        Args:
            user:       Requesting user (for visibility filtering).
            filters:    dict from SearchForm.cleaned_data.
            base_qs:    Optional pre-filtered queryset.

        Returns:
            QuerySet[EDMSDocument]
        """
        from edms.models import EDMSDocument
        from edms.services.permission_service import PermissionService

        qs = PermissionService.get_visible_queryset(user, base_qs)

        q = filters.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(title__icontains=q)              |
                Q(description__icontains=q)        |
                Q(keywords__icontains=q)           |
                Q(reference_number__icontains=q)   |
                Q(file_name__icontains=q)          |
                Q(ocr_text__icontains=q)           |
                Q(po_number__icontains=q)          |
                Q(invoice_number__icontains=q)     |
                Q(vendor__name__icontains=q)       |
                Q(vendor__gst_number__icontains=q) |
                Q(vendor__pan_number__icontains=q) |
                Q(company__company_name__icontains=q) |
                Q(company__gst_number__icontains=q)   |
                Q(company__pan_number__icontains=q)   |
                Q(tags__name__icontains=q)
            ).distinct()

        if cat := filters.get('category'):
            qs = qs.filter(category=cat)
        if dept := filters.get('department'):
            qs = qs.filter(department=dept)
        if vendor := filters.get('vendor'):
            qs = qs.filter(vendor=vendor)
        if doc_type := filters.get('document_type'):
            qs = qs.filter(document_type=doc_type)
        if access := filters.get('access_level'):
            qs = qs.filter(access_level=access)
        if approval := filters.get('approval_status'):
            qs = qs.filter(approval_status=approval)
        if ext := filters.get('file_extension'):
            qs = qs.filter(file_extension__iexact=ext)

        # Date ranges
        if date_from := filters.get('date_from'):
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to := filters.get('date_to'):
            qs = qs.filter(created_at__date__lte=date_to)
        if expiry_from := filters.get('expiry_from'):
            qs = qs.filter(expiry_date__gte=expiry_from)
        if expiry_to := filters.get('expiry_to'):
            qs = qs.filter(expiry_date__lte=expiry_to)

        # Amount range
        if amount_min := filters.get('amount_min'):
            qs = qs.filter(amount__gte=amount_min)
        if amount_max := filters.get('amount_max'):
            qs = qs.filter(amount__lte=amount_max)

        # Sort
        sort = filters.get('sort', '-created_at')
        allowed_sorts = {
            'created_at', '-created_at', 'title', '-title',
            'expiry_date', '-expiry_date', 'file_size', '-file_size',
        }
        if sort in allowed_sorts:
            qs = qs.order_by(sort)

        return qs


# ─── VersionService ───────────────────────────────────────────────────────────

class VersionService:
    """Manages version history for EDMS documents."""

    @staticmethod
    def get_versions(document):
        """Return all versions ordered newest-first."""
        return document.versions.select_related('uploaded_by').order_by('-version_number')

    @staticmethod
    def get_version(document, version_number):
        """Return a specific version or raise DoesNotExist."""
        return document.versions.get(version_number=version_number)

    @staticmethod
    def make_current(document, version_number, user, request=None):
        """Roll back to a previous version (makes it the current version)."""
        from edms.services.audit_service import AuditService

        version = VersionService.get_version(document, version_number)

        # Update is_current flags
        document.versions.filter(is_current=True).update(is_current=False)
        version.is_current = True
        version.save(update_fields=['is_current'])

        # Sync document cached metadata
        document.current_version = version.version_number
        document.file_name       = version.file_name
        document.file_size       = version.file_size
        document.mime_type       = version.mime_type
        document.file_extension  = version.file_extension
        document.file_hash       = version.file_hash
        document.save(update_fields=[
            'current_version', 'file_name', 'file_size',
            'mime_type', 'file_extension', 'file_hash', 'updated_at',
        ])

        AuditService.log(
            action='restore',
            request=request,
            user=user,
            document=document,
            description=f"Rolled back '{document.title}' to version v{version_number}",
        )
        return version


# ─── ReportService ────────────────────────────────────────────────────────────

class ReportService:
    """Generate EDMS reports as queryset data for views/exports."""

    @staticmethod
    def upload_report(filters=None):
        """Documents uploaded in a date range."""
        from edms.models import EDMSDocument
        qs = EDMSDocument.objects.filter(is_deleted=False).select_related(
            'category', 'department', 'owner', 'vendor',
        )
        if filters:
            if d := filters.get('date_from'):
                qs = qs.filter(created_at__date__gte=d)
            if d := filters.get('date_to'):
                qs = qs.filter(created_at__date__lte=d)
        return qs.order_by('-created_at')

    @staticmethod
    def download_report(filters=None):
        """Download events in a date range."""
        from edms.models import EDMSDocumentDownload
        qs = EDMSDocumentDownload.objects.select_related(
            'document', 'downloaded_by',
        )
        if filters:
            if d := filters.get('date_from'):
                qs = qs.filter(created_at__date__gte=d)
            if d := filters.get('date_to'):
                qs = qs.filter(created_at__date__lte=d)
        return qs.order_by('-created_at')

    @staticmethod
    def expiry_report():
        """Documents expiring in next 90 days."""
        from edms.models import EDMSDocument
        today = timezone.localdate()
        return EDMSDocument.objects.filter(
            is_deleted=False,
            expiry_date__gte=today,
            expiry_date__lte=today + timezone.timedelta(days=90),
        ).select_related('category', 'department').order_by('expiry_date')

    @staticmethod
    def vendor_report():
        """Documents grouped by vendor."""
        from edms.models import EDMSDocument
        return (
            EDMSDocument.objects
            .filter(is_deleted=False, vendor__isnull=False)
            .values('vendor__name', 'vendor__gst_number')
            .annotate(doc_count=Count('id'))
            .order_by('-doc_count')
        )

    @staticmethod
    def storage_report():
        """Storage usage by category."""
        from edms.models import EDMSDocument
        return (
            EDMSDocument.objects
            .filter(is_deleted=False)
            .values('category__name')
            .annotate(
                doc_count=Count('id'),
                total_size=Sum('file_size'),
            )
            .order_by('-total_size')
        )
