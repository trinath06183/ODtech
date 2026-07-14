"""
AuditService
============
Central service for creating immutable audit log entries.
All EDMS actions MUST go through this service for consistent logging.
"""

import logging
from django.utils import timezone

logger = logging.getLogger('edms.audit')


class AuditService:
    """Creates and retrieves EDMSAuditLog records."""

    @staticmethod
    def _parse_user_agent(user_agent_string):
        """Extract browser and OS from User-Agent header."""
        ua = user_agent_string or ''
        browser = 'Unknown'
        os_name = 'Unknown'
        try:
            # Very lightweight detection — replace with `user-agents` library for production
            ua_lower = ua.lower()
            if 'edg' in ua_lower:
                browser = 'Edge'
            elif 'chrome' in ua_lower:
                browser = 'Chrome'
            elif 'firefox' in ua_lower:
                browser = 'Firefox'
            elif 'safari' in ua_lower:
                browser = 'Safari'
            elif 'opera' in ua_lower or 'opr' in ua_lower:
                browser = 'Opera'

            if 'windows' in ua_lower:
                os_name = 'Windows'
            elif 'mac os' in ua_lower or 'macintosh' in ua_lower:
                os_name = 'macOS'
            elif 'linux' in ua_lower:
                os_name = 'Linux'
            elif 'android' in ua_lower:
                os_name = 'Android'
            elif 'iphone' in ua_lower or 'ipad' in ua_lower:
                os_name = 'iOS'
        except Exception:
            pass
        return browser, os_name

    @staticmethod
    def _get_ip(request):
        """Extract real IP from request, respecting proxy headers."""
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', '')

    @classmethod
    def log(
        cls,
        action,
        request=None,
        user=None,
        document=None,
        description='',
        success=True,
        failure_reason='',
        extra_data=None,
    ):
        """
        Create one EDMSAuditLog record.

        Args:
            action (str):       One of EDMSAuditLog.ACTION_* constants.
            request:            Django HttpRequest (optional but recommended).
            user:               User performing the action; falls back to request.user.
            document:           EDMSDocument instance (optional).
            description (str):  Human-readable description of the event.
            success (bool):     Whether the action succeeded.
            failure_reason:     Short reason for failure.
            extra_data (dict):  Any additional structured data to store.

        Returns:
            EDMSAuditLog instance or None on error.
        """
        from edms.models import EDMSAuditLog  # deferred to avoid circular imports

        try:
            # Resolve user
            if user is None and request is not None:
                user = getattr(request, 'user', None)
            if user and not getattr(user, 'is_authenticated', False):
                user = None

            # Request context
            ip_address  = cls._get_ip(request) if request else ''
            user_agent  = request.META.get('HTTP_USER_AGENT', '') if request else ''
            browser, os_name = cls._parse_user_agent(user_agent)

            # User metadata snapshot
            username_cached = ''
            user_role       = ''
            department_name = ''
            if user:
                username_cached = user.get_full_name() or user.username
                user_role       = getattr(user, 'role', '')
                # Try to find department from EDMS profile
                try:
                    from edms.models import Department
                    dept = Department.objects.filter(head=user).first()
                    if dept:
                        department_name = dept.name
                except Exception:
                    pass

            # Document metadata snapshot
            document_title = ''
            if document:
                document_title = getattr(document, 'title', str(document))

            log_entry = EDMSAuditLog.objects.create(
                user=user,
                username_cached=username_cached,
                user_role=user_role,
                department_name=department_name,
                action=action,
                document=document,
                document_title=document_title,
                description=description,
                extra_data=extra_data or {},
                ip_address=ip_address or None,
                user_agent=user_agent,
                browser=browser,
                operating_system=os_name,
                success=success,
                failure_reason=failure_reason,
                timestamp=timezone.now(),
            )
            logger.info(
                "[EDMS AUDIT] %s | user=%s | doc=%s | success=%s",
                action, username_cached, document_title, success,
            )
            return log_entry

        except Exception as exc:
            logger.error("[EDMS AUDIT] Failed to write audit log: %s", exc)
            return None

    @classmethod
    def log_from_request(cls, action, request, document=None, **kwargs):
        """Convenience wrapper that always passes request."""
        return cls.log(action=action, request=request, document=document, **kwargs)
