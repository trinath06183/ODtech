"""
EDMS Mixins
===========
Reusable CBV mixins for authentication and RBAC enforcement.
"""

import logging
from urllib.parse import quote

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic.base import ContextMixin

from edms.services.permission_service import PermissionService

logger = logging.getLogger('edms.mixins')


class EDMSLoginRequiredMixin:
    """Redirect unauthenticated users to login."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            path = quote(request.get_full_path())
            return redirect(f"{reverse('login')}?next={path}")
        return super().dispatch(request, *args, **kwargs)


class EDMSPermissionMixin(EDMSLoginRequiredMixin):
    """
    Require a specific EDMS permission.
    Set `edms_permission` on the view class.
    """
    edms_permission = None

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if isinstance(response, type(redirect('/'))):
            return response

        perm = self.edms_permission
        if perm and not PermissionService.has_permission(request.user, perm):
            from edms.services.audit_service import AuditService
            from edms.models import EDMSAuditLog
            AuditService.log(
                action=EDMSAuditLog.ACTION_FAILED_ACCESS,
                request=request,
                description=f"Denied '{perm}' on {request.path}",
                success=False,
                failure_reason=f"Role '{getattr(request.user, 'role', '')}' lacks '{perm}'",
            )
            messages.error(
                request,
                f"Access Denied — you need '{perm}' permission to access this page.",
            )
            return redirect('edms:dashboard')
        return super().dispatch(request, *args, **kwargs)


class EDMSDocumentPermissionMixin(EDMSLoginRequiredMixin):
    """
    Check per-document permission before allowing view access.
    Requires `document` to be set on the view (e.g. via get_object()).
    Set `edms_permission = 'view'|'download'|'delete'|…`
    """
    edms_permission = 'view'

    def get_document(self):
        """Override if the view doesn't use self.object."""
        return getattr(self, 'object', None)

    def check_document_permission(self, request, document):
        """Run permission check and redirect on failure."""
        from edms.services.audit_service import AuditService
        from edms.models import EDMSAuditLog

        allowed, reason = PermissionService.has_document_access(
            request.user, document, self.edms_permission
        )
        if not allowed:
            AuditService.log(
                action=EDMSAuditLog.ACTION_FAILED_ACCESS,
                request=request,
                document=document,
                description=f"Denied '{self.edms_permission}' on '{document.title}'",
                success=False,
                failure_reason=reason,
            )
            messages.error(request, f"Access denied: {reason}")
            return redirect('edms:dashboard')
        return None


class EDMSContextMixin(ContextMixin):
    """Add common context variables to every EDMS template."""
    page_title = 'EDMS'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        request = self.request
        ctx['page_title'] = self.page_title
        ctx['edms_user_role'] = getattr(request.user, 'role', '')
        ctx['can_upload']   = PermissionService.has_permission(request.user, 'upload')
        ctx['can_approve']  = PermissionService.has_permission(request.user, 'approve')
        ctx['can_delete']   = PermissionService.has_permission(request.user, 'delete')
        ctx['can_settings'] = PermissionService.has_permission(request.user, 'manage_settings')
        ctx['can_audit']    = PermissionService.has_permission(request.user, 'view_audit_log')
        ctx['can_reports']  = PermissionService.has_permission(request.user, 'view_reports')

        # Pending approvals badge
        try:
            from edms.models import EDMSDocument
            ctx['pending_approvals_count'] = (
                EDMSDocument.objects.filter(is_deleted=False, approval_status='pending').count()
                if ctx['can_approve'] else 0
            )
        except Exception:
            ctx['pending_approvals_count'] = 0

        return ctx
