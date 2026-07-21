from django.shortcuts import redirect
from django.urls import reverse

class OnboardingMiddleware:
    """
    Middleware that forces authenticated users who have not completed their
    onboarding profile setup to redirect to the onboarding page.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Check if user has completed onboarding profile setup
            if not getattr(request.user, 'is_onboarded', True):
                allowed_paths = [
                    reverse('onboarding'),
                    reverse('logout'),
                ]
                path = request.path
                # Allow access to onboarding, logout, admin console, static/media, and mobile upload pages
                is_allowed = (
                    any(path == p for p in allowed_paths)
                    or path.startswith('/admin/')
                    or path.startswith('/static/')
                    or path.startswith('/media/')
                    or path.startswith('/mobile/upload/')  # QR phone upload — no onboarding needed
                )
                if not is_allowed:
                    return redirect(reverse('onboarding'))

        response = self.get_response(request)
        return response
