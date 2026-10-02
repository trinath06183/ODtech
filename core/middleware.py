import json
import logging
from django.utils.deprecation import MiddlewareMixin
from core.models import SystemActivityLog

logger = logging.getLogger(__name__)


def _get_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class ActivityTrackingMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Always inject user/ip into thread-local for audit signals
        from core.audit import set_current_request
        if hasattr(request, 'user') and request.user.is_authenticated:
            set_current_request(request.user, _get_ip(request))
        else:
            set_current_request(None, _get_ip(request))

        # Log state-changing HTTP methods to SystemActivityLog
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return

        if request.method not in ('POST', 'PUT', 'DELETE', 'PATCH'):
            return

        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            return

        # Safely extract POST data, hiding passwords
        payload = {}
        if request.POST:
            for key, value in request.POST.items():
                if 'password' in key.lower():
                    payload[key] = '********'
                elif 'csrf' in key.lower():
                    continue
                else:
                    payload[key] = value

        try:
            SystemActivityLog.objects.create(
                user=request.user,
                method=request.method,
                path=request.path,
                ip_address=_get_ip(request),
                payload=payload,
            )
        except Exception as e:
            logger.error(f"Failed to save SystemActivityLog: {e}")


