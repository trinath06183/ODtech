"""
core/audit_views.py
====================
AuditLogView — field-level change history for Admin users.
Imported and registered in core/urls.py.
"""
from django.views.generic import ListView
from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from core.models import AuditLog


class AuditLogView(ListView):
    """
    Shows every CREATE / UPDATE / DELETE with before/after field values.
    Admin-only, requires the same session-unlock as system-logs.
    """
    template_name = 'core/audit_log.html'
    model = AuditLog
    context_object_name = 'logs'
    paginate_by = 50

    def dispatch(self, request, *args, **kwargs):
        if getattr(request.user, 'role', '') != 'Admin':
            messages.error(request, 'Only Admins can view audit logs.')
            return redirect('dashboard')

        unlocked_until = request.session.get('logs_unlocked_until')
        if not unlocked_until:
            return redirect('log_unlock')

        from datetime import datetime
        try:
            unlock_time = datetime.fromisoformat(unlocked_until)
            if unlock_time.tzinfo is None:
                from django.utils.timezone import make_aware
                unlock_time = make_aware(unlock_time)
            if timezone.now() > unlock_time:
                messages.warning(request, 'Log access expired. Re-enter your password.')
                return redirect('log_unlock')
        except ValueError:
            return redirect('log_unlock')

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        qs = AuditLog.objects.select_related('user', 'content_type')

        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(object_repr__icontains=q)

        action = self.request.GET.get('action', '').strip()
        if action:
            qs = qs.filter(action=action.upper())

        model_name = self.request.GET.get('model', '').strip()
        if model_name:
            qs = qs.filter(content_type__model=model_name.lower())

        user_id = self.request.GET.get('user', '').strip()
        if user_id:
            qs = qs.filter(user_id=user_id)

        start_date = self.request.GET.get('start_date', '').strip()
        end_date = self.request.GET.get('end_date', '').strip()
        if start_date:
            qs = qs.filter(timestamp__date__gte=start_date)
        if end_date:
            qs = qs.filter(timestamp__date__lte=end_date)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        ctx['model_choices'] = (
            ContentType.objects.filter(audit_logs__isnull=False)
            .values_list('model', flat=True).distinct().order_by('model')
        )
        ctx['user_choices'] = (
            User.objects.filter(core_audit_logs__isnull=False)
            .distinct().order_by('username')
        )
        ctx['action_choices'] = AuditLog.ACTION_CHOICES
        ctx['filter_q'] = self.request.GET.get('q', '')
        ctx['filter_action'] = self.request.GET.get('action', '')
        ctx['filter_model'] = self.request.GET.get('model', '')
        ctx['filter_user'] = self.request.GET.get('user', '')
        ctx['filter_start'] = self.request.GET.get('start_date', '')
        ctx['filter_end'] = self.request.GET.get('end_date', '')
        return ctx
