from functools import wraps
from django.shortcuts import redirect
from django.urls import reverse
from django.contrib import messages
from urllib.parse import quote


def login_required(view_func):
    """Redirect unauthenticated users to the custom login page."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            path = quote(request.get_full_path())
            return redirect(f"{reverse('login')}?next={path}")
        return view_func(request, *args, **kwargs)
    return wrapper


def role_required(*allowed_roles):
    """
    Allow only users whose role is in allowed_roles.
    Usage: @role_required('Admin', 'Accountant')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                path = quote(request.get_full_path())
                return redirect(f"{reverse('login')}?next={path}")
            user_role = getattr(request.user, 'role', None)
            if user_role not in allowed_roles:
                messages.error(
                    request,
                    f"Access denied. This section requires one of these roles: {', '.join(allowed_roles)}."
                )
                return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator

def require_permission(section, access_type='read'):
    """
    Allow only users with explicit read or write access to a section.
    Admins and Managing Directors bypass this check automatically via model.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                path = quote(request.get_full_path())
                return redirect(f"{reverse('login')}?next={path}")
                
            if request.user.has_section_perm(section, access_type):
                return view_func(request, *args, **kwargs)
                
            messages.error(
                request,
                f"Access denied. You do not have '{access_type}' permission for the {section} section."
            )
            return redirect('dashboard')
        return wrapper
    return decorator
