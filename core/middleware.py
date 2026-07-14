import json
import logging
from django.utils.deprecation import MiddlewareMixin
from core.models import SystemActivityLog

logger = logging.getLogger(__name__)

class ActivityTrackingMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return

        # We only log state-changing methods as per user request
        if request.method not in ('POST', 'PUT', 'DELETE', 'PATCH'):
            return

        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            return

        # Try to extract the IP address
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')

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
                ip_address=ip,
                payload=payload,
            )
        except Exception as e:
            logger.error(f"Failed to save SystemActivityLog: {e}")

