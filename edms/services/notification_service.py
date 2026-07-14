"""
NotificationService
===================
Handles both email and in-app notifications for EDMS events.
Uses Django's built-in email backend (configured via settings).
"""

import logging
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger('edms.notification')
User = get_user_model()


class NotificationService:
    """Send email and in-app notifications for EDMS events."""

    # ── Email Templates ───────────────────────────────────────────────────────
    TEMPLATE_MAP = {
        'download':  'edms/emails/document_downloaded.html',
        'delete':    'edms/emails/document_deleted.html',
        'upload':    'edms/emails/document_uploaded.html',
        'modify':    'edms/emails/document_modified.html',
        'share':     'edms/emails/document_shared.html',
        'approve':   'edms/emails/document_approved.html',
        'expiry':    'edms/emails/document_expiry.html',
        'generic':   'edms/emails/generic_notification.html',
    }

    # ── Public Methods ────────────────────────────────────────────────────────

    @classmethod
    def notify_md(cls, event_type, document, actor_request, reason='', extra_context=None):
        """
        Send email notification to Managing Director (and any configured
        EDMS_NOTIFY_EMAILS addresses) for security-critical events:
        download, delete, modify, share.

        Args:
            event_type (str):   One of 'download', 'delete', 'upload', 'modify', 'share'.
            document:           EDMSDocument instance.
            actor_request:      HttpRequest of the user who triggered the event.
            reason (str):       User-provided reason (for delete/share).
            extra_context:      Additional template variables.
        """
        recipients = cls._get_md_recipients()
        if not recipients:
            logger.warning("[EDMS NOTIFY] No MD/notify recipients configured — skipping email.")
            return

        context = cls._build_context(event_type, document, actor_request, reason, extra_context)
        template = cls.TEMPLATE_MAP.get(event_type, cls.TEMPLATE_MAP['generic'])

        subject = cls._build_subject(event_type, document)
        cls._send_email(recipients=recipients, subject=subject,
                        template=template, context=context)

        # Also create in-app notifications for MD users
        cls._create_inapp_for_md(
            document=document,
            title=subject,
            message=context.get('description', f"EDMS event: {event_type}"),
        )

    @classmethod
    def notify_user(cls, user, title, message, document=None, action_url=''):
        """Create an in-app notification for a specific user."""
        cls._create_inapp(
            recipient=user,
            document=document,
            title=title,
            message=message,
            action_url=action_url,
        )

    @classmethod
    def notify_approvers(cls, document, uploader_request):
        """
        Notify all users with 'approve' permission (Admin, Managing Director,
        Director) when a new document is uploaded pending approval.
        """
        approver_roles = ('Admin', 'Managing Director', 'Director')
        approvers = User.objects.filter(
            role__in=approver_roles, is_active=True,
        ).exclude(email='')

        context = cls._build_context('upload', document, uploader_request)
        subject = f"[EDMS] New Document Pending Approval: {document.title}"
        template = cls.TEMPLATE_MAP['upload']

        emails = list(approvers.values_list('email', flat=True))
        if emails:
            cls._send_email(recipients=emails, subject=subject,
                            template=template, context=context)

        for approver in approvers:
            cls._create_inapp(
                recipient=approver,
                document=document,
                title=subject,
                message=f"A new document '{document.title}' has been uploaded and requires your approval.",
                action_url=f"/edms/document/{document.id}/",
            )

    # ── Private Helpers ───────────────────────────────────────────────────────

    @classmethod
    def _get_md_recipients(cls):
        """Return list of MD/Director email addresses."""
        # From settings
        notify_emails = [
            e.strip() for e in getattr(settings, 'EDMS_NOTIFY_EMAILS', [])
            if e.strip()
        ]
        md_email = getattr(settings, 'EDMS_MD_EMAIL', '')
        if md_email and md_email not in notify_emails:
            notify_emails.append(md_email)

        # From DB: all Managing Director / Director users with email
        md_users = User.objects.filter(
            role__in=('Managing Director', 'Director', 'Admin'),
            is_active=True,
        ).exclude(email='').values_list('email', flat=True)
        for email in md_users:
            if email not in notify_emails:
                notify_emails.append(email)

        return notify_emails

    @classmethod
    def _build_context(cls, event_type, document, request, reason='', extra=None):
        """Build template context dict."""
        actor = getattr(request, 'user', None) if request else None
        ip    = ''
        ua    = ''
        if request:
            fwd = request.META.get('HTTP_X_FORWARDED_FOR')
            ip  = fwd.split(',')[0].strip() if fwd else request.META.get('REMOTE_ADDR', '')
            ua  = request.META.get('HTTP_USER_AGENT', '')

        ctx = {
            'event_type':    event_type,
            'document':      document,
            'actor':         actor,
            'actor_name':    actor.get_full_name() or actor.username if actor else 'System',
            'actor_role':    getattr(actor, 'role', '') if actor else '',
            'department':    str(document.department) if document and document.department else '—',
            'ip_address':    ip,
            'user_agent':    ua,
            'reason':        reason,
            'timestamp':     timezone.now(),
            'description':   f"Document '{document.title}' was {event_type}d" if document else '',
        }
        if extra:
            ctx.update(extra)
        return ctx

    @classmethod
    def _build_subject(cls, event_type, document):
        labels = {
            'download': 'Downloaded',
            'delete':   'Deleted',
            'upload':   'Uploaded',
            'modify':   'Modified',
            'share':    'Shared',
            'approve':  'Approved',
        }
        label = labels.get(event_type, event_type.title())
        title = document.title if document else 'Unknown'
        return f"[EDMS Alert] Document {label}: {title}"

    @classmethod
    def _send_email(cls, recipients, subject, template, context):
        """Send HTML email with plain-text fallback."""
        try:
            html_content  = render_to_string(template, context)
            text_content  = strip_tags(html_content)
            from_email    = getattr(settings, 'DEFAULT_FROM_EMAIL', None)

            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=recipients,
            )
            email.attach_alternative(html_content, 'text/html')
            email.send(fail_silently=False)
            logger.info("[EDMS NOTIFY] Email sent → %s | subject: %s", recipients, subject)
        except Exception as exc:
            logger.error("[EDMS NOTIFY] Failed to send email: %s", exc)

    @classmethod
    def _create_inapp(cls, recipient, title, message, document=None, action_url=''):
        """Create a single EDMSNotification record."""
        try:
            from edms.models import EDMSNotification
            EDMSNotification.objects.create(
                recipient=recipient,
                document=document,
                title=title[:255],
                message=message,
                action_url=action_url,
            )
        except Exception as exc:
            logger.error("[EDMS NOTIFY] Failed to create in-app notification: %s", exc)

    @classmethod
    def _create_inapp_for_md(cls, document, title, message):
        """Create in-app notifications for all MD/Admin/Director users."""
        try:
            md_users = User.objects.filter(
                role__in=('Managing Director', 'Director', 'Admin'),
                is_active=True,
            )
            for user in md_users:
                cls._create_inapp(
                    recipient=user,
                    document=document,
                    title=title,
                    message=message,
                    action_url=f"/edms/document/{document.id}/" if document else '',
                )
        except Exception as exc:
            logger.error("[EDMS NOTIFY] Failed to create MD in-app notifications: %s", exc)
