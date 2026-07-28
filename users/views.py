from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from core.decorators import login_required, role_required
from .models import User, OTPToken


# ─── Email Helper Functions ───────────────────────────────────────────────────

def send_verification_email(request, user):
    """Generates a signed activation token and sends verification link via email."""
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    domain = request.META.get('HTTP_HOST', 'localhost:8000')
    protocol = 'https' if request.is_secure() else 'http'

    context = {
        'user': user,
        'domain': domain,
        'protocol': protocol,
        'uid': uid,
        'token': token,
    }

    subject = "Verify your email for ODtech ERP"
    html_content = render_to_string('users/verify_email_body.html', context)
    text_content = strip_tags(html_content)

    email = EmailMultiAlternatives(
        subject,
        text_content,
        from_email=None,
        to=[user.email]
    )
    email.attach_alternative(html_content, "text/html")
    email.send()


def send_otp_email(user, otp_token):
    """Sends a 6-digit OTP to the user's email for password reset."""
    context = {
        'user': user,
        'otp': otp_token.otp,
        'expires_minutes': 10,
    }
    subject = "Your ODtech ERP Password Reset OTP"
    html_content = render_to_string('users/otp_email.html', context)
    text_content = (
        f"Hello {user.username},\n\n"
        f"Your password reset OTP is: {otp_token.otp}\n\n"
        f"It expires in 10 minutes. Do not share this code with anyone.\n\n"
        f"If you did not request a password reset, please ignore this email.\n\n"
        f"ODtech ERP"
    )
    email = EmailMultiAlternatives(
        subject, text_content, from_email=None, to=[user.email]
    )
    email.attach_alternative(html_content, "text/html")
    email.send()


def send_login_otp_email(user, otp_token):
    """Sends a 6-digit OTP for 2FA login verification."""
    from django.core.mail import EmailMultiAlternatives
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags

    context = {
        'user': user,
        'otp': otp_token.otp,
    }
    subject = "Login Verification OTP — ODtech ERP"
    html_content = render_to_string('users/login_otp_email.html', context)
    text_content = strip_tags(html_content)
    email = EmailMultiAlternatives(
        subject, text_content, from_email=None, to=[user.email]
    )
    email.attach_alternative(html_content, "text/html")
    email.send()


def send_password_changed_alert(user, request=None):
    """Sends a security alert email after a successful password change."""
    from django.utils import timezone
    context = {
        'user': user,
        'timestamp': timezone.now(),
        'ip_address': (
            request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.META.get('REMOTE_ADDR', 'Unknown')
        ) if request else 'Unknown',
    }
    subject = "Password Changed — ODtech ERP Security Alert"
    html_content = render_to_string('users/password_changed_alert.html', context)
    text_content = strip_tags(html_content)
    email = EmailMultiAlternatives(
        subject, text_content, from_email=None, to=[user.email]
    )
    email.attach_alternative(html_content, "text/html")
    email.send()


# ─── Authentication ───────────────────────────────────────────────────────────

@ensure_csrf_cookie
def login_view(request):
    """Custom login page — redirects authenticated users to dashboard."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get('next') or 'dashboard'
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password. Please try again.')

    return render(request, 'users/login.html')

@ensure_csrf_cookie
def login_verify_otp(request):
    """Step 2 of 2FA login: Verify OTP"""
    if request.user.is_authenticated:
        return redirect('dashboard')
        
    uid = request.session.get('login_2fa_uid')
    if not uid:
        messages.error(request, 'Session expired. Please log in again.')
        return redirect('login')
        
    try:
        user = User.objects.get(pk=uid)
    except User.DoesNotExist:
        return redirect('login')

    if request.method == 'POST':
        otp_input = request.POST.get('otp', '').strip()
        if not otp_input:
            messages.error(request, 'Please enter the 6-digit OTP.')
        else:
            otp_token = OTPToken.objects.filter(user=user, used=False).order_by('-created_at').first()
            if not otp_token or not otp_token.is_valid():
                messages.error(request, 'OTP is invalid or has expired. Please request a new one.')
            elif otp_token.otp != otp_input:
                messages.error(request, 'Incorrect OTP. Please check and try again.')
            else:
                otp_token.used = True
                otp_token.save()
                
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                
                request.session.pop('login_2fa_uid', None)
                next_url = request.session.pop('login_next_url', 'dashboard')
                
                messages.success(request, f'Welcome back, {user.first_name or user.username}!')
                return redirect(next_url)

    return render(request, 'users/login_verify_otp.html', {'email': user.email})

def login_resend_otp(request):
    """Resend 2FA login OTP"""
    if request.method == 'POST':
        uid = request.session.get('login_2fa_uid')
        if not uid:
            messages.error(request, 'Session expired. Please start over.')
            return redirect('login')
            
        try:
            user = User.objects.get(pk=uid)
            otp_token = OTPToken.generate_for_user(user)
            send_login_otp_email(user, otp_token)
            messages.success(request, f'A new OTP has been sent to {user.email}.')
        except User.DoesNotExist:
            pass
            
    return redirect('login_verify_otp')


@login_required
def onboarding_view(request):
    """View for first-time login onboarding to complete user profile."""
    if request.user.is_onboarded:
        return redirect('dashboard')

    if request.method == 'POST':
        first_name  = request.POST.get('first_name', '').strip()
        last_name   = request.POST.get('last_name', '').strip()
        designation = request.POST.get('designation', '').strip()
        empid       = request.POST.get('empid', '').strip()

        if not first_name or not last_name or not designation or not empid:
            messages.error(request, 'All fields are required to complete onboarding.')
        elif User.objects.filter(empid=empid).exclude(pk=request.user.pk).exists():
            messages.error(request, f'Employee ID "{empid}" is already registered by another user.')
        else:
            try:
                request.user.first_name = first_name
                request.user.last_name = last_name
                request.user.designation = designation
                request.user.empid = empid
                request.user.username = empid
                request.user.is_onboarded = True
                request.user.save()
                messages.success(request, f'Profile completed successfully! Welcome to ODtech ERP.')
                return redirect('dashboard')
            except Exception as e:
                messages.error(request, f'An error occurred: {str(e)}')

    return render(request, 'users/onboarding.html')


@ensure_csrf_cookie
def verify_email_view(request, uidb64, token):
    """View to verify user email and activate the account using dynamic links."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_email_verified = True
        user.is_active = True
        user.save()

        # Auto-login the user once verified
        login(request, user)
        messages.success(request, f'Email verified successfully! Welcome to your dashboard, {user.username}.')
        return redirect('dashboard')
    else:
        return render(request, 'users/verify_email_failed.html')


@login_required
def logout_view(request):
    """POST-only logout for CSRF safety; GET redirects to login."""
    if request.method == 'POST':
        logout(request)
        messages.success(request, 'You have been signed out successfully.')
    return redirect('login')


# ─── OTP Password Reset (3-Step Flow) ────────────────────────────────────────

@ensure_csrf_cookie
def password_reset_request(request):
    """
    Step 1 — User enters their email address.
    We look up the account, generate a 6-digit OTP, and email it.
    The user's email is stored in session to carry it to step 2.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        if not email:
            messages.error(request, 'Please enter your email address.')
            return render(request, 'users/password_reset_form.html')

        try:
            user = User.objects.get(email__iexact=email, is_active=True)
        except User.DoesNotExist:
            # Silently succeed to prevent email enumeration
            messages.success(
                request,
                'If that email is registered, you will receive an OTP shortly.'
            )
            return render(request, 'users/password_reset_form.html')

        # Generate OTP and send email
        otp_token = OTPToken.generate_for_user(user)
        try:
            send_otp_email(user, otp_token)
        except Exception as e:
            print("Email sending failed:", str(e))
            messages.error(request, f'Could not send email. Please try again later.')
            return render(request, 'users/password_reset_form.html')

        # Store reset session data (email only, not OTP — never expose in session)
        request.session['otp_reset_email'] = user.email
        request.session['otp_reset_uid'] = str(user.pk)
        messages.success(
            request,
            f'A 6-digit OTP has been sent to {email}. It expires in 10 minutes.'
        )
        return redirect('password_reset_verify_otp')

    return render(request, 'users/password_reset_form.html')


@ensure_csrf_cookie
def password_reset_verify_otp(request):
    """
    Step 2 — User enters the 6-digit OTP they received by email.
    On success, session is upgraded to allow setting a new password.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    reset_email = request.session.get('otp_reset_email')
    if not reset_email:
        messages.error(request, 'Session expired. Please start the password reset again.')
        return redirect('password_reset')

    if request.method == 'POST':
        otp_input = request.POST.get('otp', '').strip()

        try:
            uid = request.session.get('otp_reset_uid')
            user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError):
            messages.error(request, 'Invalid session. Please start over.')
            return redirect('password_reset')

        # Validate OTP
        token = OTPToken.objects.filter(
            user=user,
            otp=otp_input,
            used=False,
        ).order_by('-created_at').first()

        if token is None or not token.is_valid():
            messages.error(request, 'Invalid or expired OTP. Please try again or request a new one.')
            return render(request, 'users/password_reset_otp.html', {'email': reset_email})

        # Mark token as used and allow set-password step
        token.used = True
        token.save()
        request.session['otp_reset_verified'] = True

        return redirect('password_reset_set_password')

    # GET — show the OTP entry page
    return render(request, 'users/password_reset_otp.html', {'email': reset_email})


@ensure_csrf_cookie
def password_reset_resend_otp(request):
    """Resend OTP to the email stored in session (POST only)."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    reset_email = request.session.get('otp_reset_email')
    if not reset_email:
        return redirect('password_reset')

    if request.method == 'POST':
        try:
            uid = request.session.get('otp_reset_uid')
            user = User.objects.get(pk=uid, is_active=True)
            otp_token = OTPToken.generate_for_user(user)
            send_otp_email(user, otp_token)
            messages.success(request, 'A new OTP has been sent to your email.')
        except Exception:
            messages.error(request, 'Could not resend OTP. Please try again.')

    return redirect('password_reset_verify_otp')


@ensure_csrf_cookie
def password_reset_set_password(request):
    """
    Step 3 — User sets a new password after OTP verification.
    Requires 'otp_reset_verified' flag in session.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    if not request.session.get('otp_reset_verified'):
        messages.error(request, 'Please verify your OTP before setting a new password.')
        return redirect('password_reset')

    if request.method == 'POST':
        new_password1 = request.POST.get('new_password1', '')
        new_password2 = request.POST.get('new_password2', '')

        if new_password1 != new_password2:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'users/password_reset_confirm.html')

        try:
            uid = request.session.get('otp_reset_uid')
            user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError):
            messages.error(request, 'Invalid session. Please start over.')
            return redirect('password_reset')

        try:
            validate_password(new_password1, user)
        except ValidationError as e:
            for err in e.messages:
                messages.error(request, err)
            return render(request, 'users/password_reset_confirm.html')

        user.set_password(new_password1)
        user.save()

        # Clean up session
        for key in ('otp_reset_email', 'otp_reset_uid', 'otp_reset_verified'):
            request.session.pop(key, None)

        # Send security alert email
        try:
            send_password_changed_alert(user, request)
        except Exception:
            pass  # Alert is best-effort; don't block the reset

        messages.success(request, 'Password reset successful! You can now sign in with your new password.')
        return redirect('password_reset_complete')

    return render(request, 'users/password_reset_confirm.html')


def password_reset_complete(request):
    """Final success page shown after a successful password reset."""
    return render(request, 'users/password_reset_complete.html')


# ─── User Management (Admin only) ────────────────────────────────────────────

@role_required('Admin')
def user_list(request):
    users = User.objects.all().order_by('username')
    return render(request, 'users/user_list.html', {'users': users})


@role_required('Admin')
def user_create(request):
    if request.method == 'POST':
        empid      = request.POST.get('empid', '').strip()
        email      = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name  = request.POST.get('last_name', '').strip()
        role       = request.POST.get('role', 'Staff')
        password   = request.POST.get('password', '')

        if not empid or not password or not email:
            messages.error(request, 'Employee Code, Email, and password are required.')
        elif User.objects.filter(empid=empid).exists():
            messages.error(request, f'Employee Code "{empid}" is already taken.')
        elif User.objects.filter(email=email).exists():
            messages.error(request, f'Email "{email}" is already registered.')
        elif role not in [r[0] for r in User.ROLE_CHOICES]:
            messages.error(request, 'Invalid role selected.')
        else:
            user = User(
                username=empid,
                empid=empid,
                email=email,
                first_name=first_name,
                last_name=last_name,
                role=role,
                is_active=False,  # Must verify email first
                is_email_verified=False,
                is_onboarded=False,
            )
            user.set_password(password)
            user.save()

            # Send verification email
            send_verification_email(request, user)

            messages.success(request, f'User with Employee Code "{empid}" created successfully. Verification email sent.')
            return redirect('user_list')

    return render(request, 'users/user_form.html', {
        'form_title': 'Create User',
        'submit_label': 'Create User',
        'role_choices': User.ROLE_CHOICES,
    })


@role_required('Admin')
def user_edit(request, user_id):
    target_user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        target_user.email      = request.POST.get('email', '').strip()
        target_user.first_name = request.POST.get('first_name', '').strip()
        target_user.last_name  = request.POST.get('last_name', '').strip()
        role                   = request.POST.get('role', target_user.role)
        target_user.is_active  = request.POST.get('is_active') == 'on'
        new_password           = request.POST.get('password', '').strip()

        if role not in [r[0] for r in User.ROLE_CHOICES]:
            messages.error(request, 'Invalid role selected.')
        else:
            target_user.role = role
            if new_password:
                target_user.set_password(new_password)
            target_user.save()
            messages.success(request, f'User "{target_user.username}" updated successfully.')
            return redirect('user_list')

    return render(request, 'users/user_form.html', {
        'form_title':   f'Edit User — {target_user.username}',
        'submit_label': 'Save Changes',
        'role_choices': User.ROLE_CHOICES,
        'target_user':  target_user,
    })


@role_required('Admin')
def user_delete(request, user_id):
    target_user = get_object_or_404(User, id=user_id)

    if target_user == request.user:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('user_list')

    if request.method == 'POST':
        username = target_user.username
        try:
            target_user.delete()
            messages.success(request, f'User "{username}" has been deleted.')
        except Exception as e:
            from django.db.models import ProtectedError
            if isinstance(e, ProtectedError):
                messages.error(request, f'Cannot delete user "{username}" because they are linked to existing documents or expenses. Please edit the user and set them to "Inactive" instead.')
            else:
                messages.error(request, f'An error occurred while deleting the user: {str(e)}')
        return redirect('user_list')

    # GET: show confirmation page
    return render(request, 'users/user_confirm_delete.html', {'target_user': target_user})
