"""
PermissionService
=================
RBAC (Role-Based Access Control) for the EDMS module.

Permission Matrix:
┌──────────────────────┬────┬──────┬───────┬─────────┬──────────┬────────┬────┬─────────────┬─────────┬────────┐
│ Permission           │ MD │ Dir. │ Admin │ Purchase│ Accounts │ Tender │ HR │ Engineering │ Project │ Viewer │
├──────────────────────┼────┼──────┼───────┼─────────┼──────────┼────────┼────┼─────────────┼─────────┼────────┤
│ upload               │ ✓  │  ✓   │   ✓   │    ✓    │    ✓     │   ✓    │ ✓  │      ✓      │    ✓    │   ✗    │
│ view                 │ ✓  │  ✓   │   ✓   │    ✓    │    ✓     │   ✓    │ ✓  │      ✓      │    ✓    │   ✓    │
│ preview              │ ✓  │  ✓   │   ✓   │    ✓    │    ✓     │   ✓    │ ✓  │      ✓      │    ✓    │   ✓    │
│ download             │ ✓  │  ✓   │   ✓   │    ✓    │    ✓     │   ✓    │ ✓  │      ✓      │    ✓    │   ✗    │
│ edit_metadata        │ ✓  │  ✓   │   ✓   │    ✓    │    ✓     │   ✓    │ ✓  │      ✓      │    ✓    │   ✗    │
│ delete               │ ✓  │  ✓   │   ✓   │    ✗    │    ✗     │   ✗    │ ✗  │      ✗      │    ✗    │   ✗    │
│ approve              │ ✓  │  ✓   │   ✓   │    ✗    │    ✗     │   ✗    │ ✗  │      ✗      │    ✗    │   ✗    │
│ restore              │ ✓  │  ✓   │   ✓   │    ✗    │    ✗     │   ✗    │ ✗  │      ✗      │    ✗    │   ✗    │
│ share                │ ✓  │  ✓   │   ✓   │    ✓    │    ✓     │   ✓    │ ✓  │      ✓      │    ✓    │   ✗    │
│ export               │ ✓  │  ✓   │   ✓   │    ✓    │    ✓     │   ✓    │ ✓  │      ✓      │    ✓    │   ✗    │
│ manage_categories    │ ✓  │  ✓   │   ✓   │    ✗    │    ✗     │   ✗    │ ✗  │      ✗      │    ✗    │   ✗    │
│ manage_settings      │ ✓  │  ✗   │   ✓   │    ✗    │    ✗     │   ✗    │ ✗  │      ✗      │    ✗    │   ✗    │
└──────────────────────┴────┴──────┴───────┴─────────┴──────────┴────────┴────┴─────────────┴─────────┴────────┘
"""

import logging
from django.db.models import Q

logger = logging.getLogger('edms.permissions')


# ── Permission → Allowed Roles mapping ────────────────────────────────────────

PERMISSION_ROLES = {
    'upload': {
        'Managing Director', 'Director', 'Admin',
        'Purchase', 'Accounts', 'Tender', 'HR',
        'Engineering', 'Project',
    },
    'view': {
        'Managing Director', 'Director', 'Admin',
        'Purchase', 'Accounts', 'Tender', 'HR',
        'Engineering', 'Project', 'Viewer',
    },
    'preview': {
        'Managing Director', 'Director', 'Admin',
        'Purchase', 'Accounts', 'Tender', 'HR',
        'Engineering', 'Project', 'Viewer',
    },
    'download': {
        'Managing Director', 'Director', 'Admin',
        'Purchase', 'Accounts', 'Tender', 'HR',
        'Engineering', 'Project',
    },
    'edit_metadata': {
        'Managing Director', 'Director', 'Admin',
        'Purchase', 'Accounts', 'Tender', 'HR',
        'Engineering', 'Project',
    },
    'delete': {'Managing Director', 'Director', 'Admin'},
    'approve': {'Managing Director', 'Director', 'Admin'},
    'restore': {'Managing Director', 'Director', 'Admin'},
    'share': {
        'Managing Director', 'Director', 'Admin',
        'Purchase', 'Accounts', 'Tender', 'HR',
        'Engineering', 'Project',
    },
    'export': {
        'Managing Director', 'Director', 'Admin',
        'Purchase', 'Accounts', 'Tender', 'HR',
        'Engineering', 'Project',
    },
    'manage_categories': {'Managing Director', 'Director', 'Admin'},
    'manage_settings':   {'Managing Director', 'Admin'},
    'view_audit_log':    {'Managing Director', 'Director', 'Admin'},
    'view_reports':      {'Managing Director', 'Director', 'Admin', 'Accounts'},
}

# ── Access-level visibility rules ─────────────────────────────────────────────
# Which roles can see documents at each access level?
ACCESS_VISIBILITY = {
    'public': set(PERMISSION_ROLES['view']),          # everyone
    'internal': set(PERMISSION_ROLES['view']),        # everyone (internal users only via login)
    'department': set(PERMISSION_ROLES['view']),      # further filtered by department
    'management': {'Managing Director', 'Director', 'Admin'},
    'admin':      {'Admin', 'Managing Director'},
}


class PermissionService:
    """Central RBAC service for EDMS."""

    @staticmethod
    def has_permission(user, permission):
        """
        Check if a user (by their role) has a given EDMS permission.
        Also checks per-document access grants if a document context is available.

        Args:
            user: Django User instance.
            permission (str): Permission key from PERMISSION_ROLES.

        Returns:
            bool
        """
        if not user or not getattr(user, 'is_authenticated', False):
            return False

        # Superusers bypass all checks
        if user.is_superuser:
            return True

        role = getattr(user, 'role', '')
        allowed = PERMISSION_ROLES.get(permission, set())
        return role in allowed

    @staticmethod
    def has_document_access(user, document, permission='view'):
        """
        Check if a user can perform `permission` on a specific `document`.

        Evaluation order:
          1. Superuser → always True.
          2. Role-level permission check.
          3. Document access_level visibility check.
          4. Department filter (for department-level access).
          5. Per-document access grants.

        Returns:
            (bool, str) — (access_granted, reason)
        """
        if not user or not getattr(user, 'is_authenticated', False):
            return False, 'Not authenticated'

        if user.is_superuser:
            # Even superusers shouldn't delete if global setting is off, but we'll let them for now,
            # or actually, we should enforce the setting globally for all.
            if permission == 'delete':
                from config.models import CompanyProfile
                company = CompanyProfile.objects.first()
                if company and not company.allow_document_deletion:
                    return False, 'Document deletion is globally disabled in system settings.'
            return True, 'Superuser'

        if permission == 'delete':
            from config.models import CompanyProfile
            company = CompanyProfile.objects.first()
            if company and not company.allow_document_deletion:
                return False, 'Document deletion is globally disabled in system settings.'

        # Soft-deleted documents: only admins can see them
        if document.is_deleted:
            if PermissionService.has_permission(user, 'restore'):
                return True, 'Admin/restore permission'
            return False, 'Document has been deleted'

        role = getattr(user, 'role', '')

        # 1. Check global role permission
        if not PermissionService.has_permission(user, permission):
            # Check if there's an explicit per-document grant
            return PermissionService._check_explicit_grant(user, role, document, permission)

        # 2. Check access level visibility
        doc_access_level = document.access_level
        visible_roles = ACCESS_VISIBILITY.get(doc_access_level, set())
        if role not in visible_roles:
            return PermissionService._check_explicit_grant(user, role, document, permission)

        # 3. Department-only filter
        if doc_access_level == 'department':
            if document.department_id and user.role not in ('Managing Director', 'Director', 'Admin'):
                # Check if user is in the same department
                user_dept_ids = _get_user_department_ids(user)
                if document.department_id not in user_dept_ids:
                    return PermissionService._check_explicit_grant(user, role, document, permission)

        return True, 'Role permission granted'

    @staticmethod
    def _check_explicit_grant(user, role, document, permission):
        """Check EDMSDocumentAccess records for explicit grants."""
        from edms.models import EDMSDocumentAccess
        from django.utils import timezone
        grant = EDMSDocumentAccess.objects.filter(
            document=document,
            permission=permission,
        ).filter(
            Q(user=user) | Q(role=role)
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        ).first()
        if grant:
            return True, 'Explicit access grant'
        return False, f"Role '{role}' does not have '{permission}' on this document"

    @staticmethod
    def get_visible_queryset(user, base_qs=None):
        """
        Filter an EDMSDocument queryset to only those the user can view.
        Always excludes soft-deleted unless user has restore permission.
        """
        from edms.models import EDMSDocument
        qs = base_qs if base_qs is not None else EDMSDocument.objects.all()

        if not user or not getattr(user, 'is_authenticated', False):
            return qs.none()

        if user.is_superuser:
            return qs

        role = getattr(user, 'role', '')

        # Exclude deleted unless admin
        if not PermissionService.has_permission(user, 'restore'):
            qs = qs.filter(is_deleted=False)

        # Filter by access level
        if role in ('Managing Director', 'Director', 'Admin'):
            # Sees everything
            pass
        elif role == 'Viewer':
            qs = qs.filter(access_level__in=('public', 'internal'))
        else:
            # Department-level: sees public, internal, and own-department docs
            user_dept_ids = _get_user_department_ids(user)
            qs = qs.filter(
                Q(access_level__in=('public', 'internal')) |
                Q(access_level='department', department_id__in=user_dept_ids)
            )

        return qs


def _get_user_department_ids(user):
    """Return set of department IDs the user belongs to (via head role)."""
    from edms.models import Department
    return set(
        Department.objects.filter(head=user).values_list('id', flat=True)
    )


def require_edms_permission(permission):
    """
    Class-based view mixin decorator factory.
    Usage:  @require_edms_permission('upload')
    """
    from functools import wraps
    from django.contrib import messages
    from django.shortcuts import redirect

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.urls import reverse
                from urllib.parse import quote
                path = quote(request.get_full_path())
                return redirect(f"{reverse('login')}?next={path}")
            if not PermissionService.has_permission(request.user, permission):
                messages.error(
                    request,
                    f"Access denied. You need '{permission}' permission to perform this action."
                )
                return redirect('edms:dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
