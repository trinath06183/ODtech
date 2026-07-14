"""
EDMS Signals
============
Django signals for automatic audit logging, notifications,
and housekeeping on EDMS model events.
"""

import logging
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver

logger = logging.getLogger('edms.signals')


@receiver(post_save, sender='edms.EDMSDocument')
def on_document_saved(sender, instance, created, **kwargs):
    """Log document creation (upload is logged separately by service, this catches admin saves)."""
    if created:
        logger.info("[EDMS SIGNAL] Document created: %s (id=%s)", instance.title, instance.id)


@receiver(post_save, sender='edms.EDMSDocumentVersion')
def on_version_saved(sender, instance, created, **kwargs):
    """Log every new version creation."""
    if created:
        logger.info(
            "[EDMS SIGNAL] Version v%s created for document '%s'",
            instance.version_number, instance.document.title,
        )


@receiver(post_save, sender='edms.EDMSDocument')
def on_document_approved(sender, instance, created, update_fields, **kwargs):
    """When approval_status changes to 'approved', notify the uploader."""
    if not created and update_fields and 'approval_status' in update_fields:
        if instance.approval_status == 'approved':
            try:
                from edms.services.notification_service import NotificationService
                NotificationService.notify_user(
                    user=instance.uploaded_by,
                    title=f"Document Approved: {instance.title}",
                    message=(
                        f"Your document '{instance.title}' has been approved "
                        f"by {instance.approved_by.get_full_name() if instance.approved_by else 'an administrator'}."
                    ),
                    document=instance,
                    action_url=f"/edms/document/{instance.id}/",
                )
            except Exception as exc:
                logger.error("[EDMS SIGNAL] Approval notification failed: %s", exc)


@receiver(post_save, sender='edms.EDMSDocumentDownload')
def on_document_downloaded(sender, instance, created, **kwargs):
    """After every download record is saved, fire notification to MD."""
    if created:
        try:
            from edms.services.notification_service import NotificationService
            # We don't have request here, so we pass None and build minimal context
            NotificationService._create_inapp_for_md(
                document=instance.document,
                title=f"Document Downloaded: {instance.document.title}",
                message=(
                    f"Document '{instance.document.title}' was downloaded by "
                    f"{instance.downloaded_by.get_full_name() if instance.downloaded_by else 'Unknown User'} "
                    f"from IP {instance.ip_address or 'unknown'}."
                ),
            )
        except Exception as exc:
            logger.error("[EDMS SIGNAL] Download notification failed: %s", exc)
