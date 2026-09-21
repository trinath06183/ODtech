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

        # Check if request expects JSON / AJAX
        is_api = (
            request.path.startswith('/api/') or
            '/api/' in request.path or
            request.headers.get('x-requested-with') == 'XMLHttpRequest' or
            'application/json' in request.headers.get('accept', '') or
            getattr(request, 'content_type', '') == 'application/json'
        )

        error_log = None
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
        except Exception as e:
            logger.error(f"Failed to save ErrorLog: {e}")

        ref_id = str(error_log.reference_id) if error_log else 'ERR-' + str(int(timezone.now().timestamp())) if 'timezone' in globals() else 'ERR-UNSAVED'

        # If AJAX / API request, return JSON so frontend can display the exact error
        if is_api:
            from django.http import JsonResponse
            return JsonResponse({
                'success': False,
                'error': f"{exception.__class__.__name__}: {str(exception)}",
                'error_type': exception.__class__.__name__,
                'error_message': str(exception),
                'stack_trace': traceback.format_exc(),
                'reference_id': ref_id,
            }, status=500)

        # For regular web page requests, render 500.html with full error details
        if not settings.DEBUG:
            from django.utils import timezone as tz
            context = {
                'reference_id': ref_id,
                'error_type': exception.__class__.__name__,
                'error_message': str(exception) or 'No error message provided.',
                'stack_trace': traceback.format_exc(),
                'url': request.build_absolute_uri(),
                'method': request.method,
                'timestamp': tz.now(),
            }
            return render(request, '500.html', context, status=500)

        return None
