"""
EDMS Template Tags and Filters
================================
Usage in templates: {% load edms_tags %}
"""

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from edms.services.permission_service import PermissionService

register = template.Library()


# ─── Permission Filters ───────────────────────────────────────────────────────

@register.filter
def edms_can(user, permission):
    """
    Check if user has the given EDMS permission.
    Usage: {% if request.user|edms_can:'upload' %}
    """
    return PermissionService.has_permission(user, permission)


@register.simple_tag
def edms_permission(user, permission):
    """
    Returns True/False as a tag.
    Usage: {% edms_permission request.user 'download' as can_download %}
    """
    return PermissionService.has_permission(user, permission)


# ─── File Size Filter ─────────────────────────────────────────────────────────

@register.filter
def file_size(value):
    """
    Convert bytes to human-readable size.
    Usage: {{ document.file_size|file_size }}
    """
    try:
        size = int(value)
    except (TypeError, ValueError):
        return '—'
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# ─── File Extension Badge ─────────────────────────────────────────────────────

EXT_COLORS = {
    '.pdf':  ('bg-red-100 text-red-700',    '📄 PDF'),
    '.doc':  ('bg-blue-100 text-blue-700',  '📝 DOC'),
    '.docx': ('bg-blue-100 text-blue-700',  '📝 DOCX'),
    '.xls':  ('bg-green-100 text-green-700','📊 XLS'),
    '.xlsx': ('bg-green-100 text-green-700','📊 XLSX'),
    '.ppt':  ('bg-orange-100 text-orange-700', '📑 PPT'),
    '.pptx': ('bg-orange-100 text-orange-700', '📑 PPTX'),
    '.jpg':  ('bg-purple-100 text-purple-700', '🖼 JPG'),
    '.jpeg': ('bg-purple-100 text-purple-700', '🖼 JPEG'),
    '.png':  ('bg-purple-100 text-purple-700', '🖼 PNG'),
    '.zip':  ('bg-yellow-100 text-yellow-700', '🗜 ZIP'),
    '.txt':  ('bg-gray-100 text-gray-700',  '📃 TXT'),
    '.csv':  ('bg-teal-100 text-teal-700',  '📋 CSV'),
}

@register.filter
def file_type_badge(extension):
    """
    Render a coloured badge for a file extension.
    Usage: {{ document.file_extension|file_type_badge }}
    """
    ext = (extension or '').lower()
    css, label = EXT_COLORS.get(ext, ('bg-gray-100 text-gray-600', ext.upper() or 'FILE'))
    return format_html(
        '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium {}">{}</span>',
        css, label,
    )


# ─── Approval Status Badge ────────────────────────────────────────────────────

APPROVAL_STYLES = {
    'pending':  ('bg-yellow-100 text-yellow-700', '⏳ Pending'),
    'approved': ('bg-green-100 text-green-700',   '✅ Approved'),
    'rejected': ('bg-red-100 text-red-700',        '❌ Rejected'),
}

@register.filter
def approval_badge(status):
    """
    Render a coloured badge for approval status.
    Usage: {{ document.approval_status|approval_badge }}
    """
    css, label = APPROVAL_STYLES.get(status, ('bg-gray-100 text-gray-600', status))
    return format_html(
        '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium {}">{}</span>',
        css, label,
    )


# ─── Access Level Badge ───────────────────────────────────────────────────────

ACCESS_STYLES = {
    'public':     ('bg-green-100 text-green-700',   '🌐 Public'),
    'internal':   ('bg-blue-100 text-blue-700',     '🏢 Internal'),
    'department': ('bg-purple-100 text-purple-700', '🏬 Department'),
    'management': ('bg-orange-100 text-orange-700', '👔 Management'),
    'admin':      ('bg-red-100 text-red-700',       '🔐 Admin'),
}

@register.filter
def access_level_badge(level):
    """
    Render a coloured badge for access level.
    Usage: {{ document.access_level|access_level_badge }}
    """
    css, label = ACCESS_STYLES.get(level, ('bg-gray-100 text-gray-600', level))
    return format_html(
        '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium {}">{}</span>',
        css, label,
    )


# ─── Role Badge ───────────────────────────────────────────────────────────────

ROLE_STYLES = {
    'Managing Director': 'bg-violet-100 text-violet-700',
    'Director':          'bg-indigo-100 text-indigo-700',
    'Admin':             'bg-blue-100 text-blue-700',
    'Purchase':          'bg-teal-100 text-teal-700',
    'Accounts':          'bg-green-100 text-green-700',
    'Tender':            'bg-yellow-100 text-yellow-700',
    'HR':                'bg-pink-100 text-pink-700',
    'Engineering':       'bg-orange-100 text-orange-700',
    'Project':           'bg-cyan-100 text-cyan-700',
    'Viewer':            'bg-gray-100 text-gray-600',
}

@register.filter
def role_badge(role):
    """
    Render a coloured badge for a user role.
    Usage: {{ request.user.role|role_badge }}
    """
    css = ROLE_STYLES.get(role, 'bg-gray-100 text-gray-600')
    return format_html(
        '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium {}">{}</span>',
        css, role or 'Unknown',
    )


# ─── Expiry Color Tag ─────────────────────────────────────────────────────────

@register.filter
def expiry_color(expiry_date):
    """Return a Tailwind CSS colour class based on expiry proximity."""
    from django.utils import timezone
    if not expiry_date:
        return 'text-gray-400'
    today = timezone.localdate()
    delta = (expiry_date - today).days
    if delta < 0:
        return 'text-red-600 font-bold'
    if delta <= 30:
        return 'text-orange-600 font-semibold'
    if delta <= 90:
        return 'text-yellow-600'
    return 'text-green-600'


# ─── Unread Notification Count ────────────────────────────────────────────────

@register.simple_tag(takes_context=True)
def unread_notifications(context):
    """Return count of unread EDMS notifications for the current user."""
    request = context.get('request')
    if not request or not request.user.is_authenticated:
        return 0
    try:
        from edms.models import EDMSNotification
        return EDMSNotification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
    except Exception:
        return 0


# ─── Preview Support ──────────────────────────────────────────────────────────

@register.filter
def can_preview(extension):
    """Return True if the extension supports in-browser preview."""
    PREVIEWABLE = {'.pdf', '.jpg', '.jpeg', '.png', '.gif', '.bmp',
                   '.webp', '.txt', '.svg', '.mp4', '.webm'}
    return (extension or '').lower() in PREVIEWABLE
