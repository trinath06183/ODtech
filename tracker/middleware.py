import threading

_thread_locals = threading.local()

def get_current_user():
    return getattr(_thread_locals, 'user', None)

class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.user = getattr(request, 'user', None)
        response = self.get_response(request)
        _thread_locals.user = None
        return response

import traceback
import json
import logging
from django.conf import settings
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin
from .models import ErrorLog

logger = logging.getLogger(__name__)

class ErrorLoggingMiddleware(MiddlewareMixin):
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def process_exception(self, request, exception):
        # Scrub sensitive data
        sensitive_keys = ['password', 'csrfmiddlewaretoken', 'card_number', 'cvv', 'credit_card', 'secret']
        post_data = {}
        if request.POST:
            for key, value in request.POST.items():
                if any(sensitive.lower() in key.lower() for sensitive in sensitive_keys):
                    post_data[key] = '*** SCRUBBED ***'
                else:
                    post_data[key] = value

        try:
            error_log = ErrorLog.objects.create(
                environment=getattr(settings, 'ENVIRONMENT', 'development') if settings.DEBUG else 'production',
                status_code=500,
                error_type=exception.__class__.__name__,
                error_message=str(exception),
                stack_trace=traceback.format_exc(),
                url=request.build_absolute_uri(),
                http_method=request.method,
                query_params=json.dumps(request.GET.dict()),
                post_data=json.dumps(post_data),
                user=request.user if hasattr(request, 'user') and request.user.is_authenticated else None,
                ip_address=self.get_client_ip(request),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            # If not in debug mode, return our custom 500 template with the reference ID
            if not settings.DEBUG:
                context = {'reference_id': error_log.reference_id}
                return render(request, '500.html', context, status=500)
                
        except Exception as e:
            # If logging fails, fall back silently so we don't cause infinite error loops
            logger.error(f"Failed to save ErrorLog: {e}")
            
        return None
