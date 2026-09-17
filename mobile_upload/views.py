"""
mobile_upload/views.py
======================
4 views powering the QR-code mobile upload feature:

  1. generate_qr_session  — Desktop: creates a session, returns JSON with token + upload URL
  2. mobile_upload_page   — Phone: renders the mobile-optimised upload page (no login needed)
  3. mobile_upload_submit — Phone: handles the actual file POST from the phone
  4. check_upload_status  — Desktop: polled every 2 s, returns JSON status
"""

import os
import mimetypes
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET

from .models import MobileUploadSession


# ── 0. QR Scanner page (camera-based QR reader) ───────────────────────────────

def qr_scanner_page(request):
    """
    GET /mobile/qr-scan/
    A standalone camera-based QR code scanner page.
    Opens the device camera, detects a QR code, and redirects to the URL found.
    No login required — it's a read-only utility.
    """
    return render(request, 'mobile_upload/qr_scanner_page.html')

# ── 1. Desktop: generate a new session and return the QR URL ──────────────────

@login_required
@require_POST
def generate_qr_session(request):
    """
    POST /mobile/generate-session/
    Creates a fresh MobileUploadSession and returns JSON so the desktop
    JavaScript can render the QR code.
    """
    session = MobileUploadSession.objects.create(created_by=request.user)

    # Build the absolute URL the phone will open
    upload_url = request.build_absolute_uri(f'/mobile/upload/{session.token}/')

    return JsonResponse({
        'token':            str(session.token),
        'upload_url':       upload_url,
        'status_url':       request.build_absolute_uri(f'/mobile/upload/{session.token}/status/'),
        'seconds_remaining': session.seconds_remaining,
    })


# ── 2. Phone: render the upload page ──────────────────────────────────────────

def mobile_upload_page(request, token):
    """
    GET /mobile/upload/<token>/
    Renders the mobile-friendly upload page.
    No login required — the token is the security.
    """
    session = get_object_or_404(MobileUploadSession, token=token)

    # Expire if past deadline
    if session.status == MobileUploadSession.STATUS_PENDING and session.is_expired:
        session.mark_expired()

    return render(request, 'mobile_upload/upload_page.html', {
        'session': session,
        'token':   str(token),
    })


# ── 3. Phone: handle the file upload POST ─────────────────────────────────────

@csrf_exempt
@require_POST
def mobile_upload_submit(request, token):
    """
    POST /mobile/upload/<token>/submit/
    Accepts the file from the phone, saves it, marks the session completed.
    Returns JSON so the phone can show a success screen.
    """
    session = get_object_or_404(MobileUploadSession, token=token)

    # Guard: already used or expired
    if session.status == MobileUploadSession.STATUS_COMPLETED:
        return JsonResponse({'error': 'This upload link has already been used.'}, status=400)

    if session.status == MobileUploadSession.STATUS_EXPIRED or session.is_expired:
        session.mark_expired()
        return JsonResponse({'error': 'This upload link has expired. Please generate a new QR code.'}, status=410)

    # Validate file presence
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'No file was received.'}, status=400)

    uploaded = request.FILES['file']

    # Size check (50 MB max, matching EDMS settings)
    max_bytes = getattr(__import__('django.conf', fromlist=['settings']).settings, 'EDMS_MAX_UPLOAD_BYTES', 50 * 1024 * 1024)
    if uploaded.size > max_bytes:
        return JsonResponse({'error': f'File is too large. Maximum size is 50 MB.'}, status=400)

    # Detect MIME type
    mime, _ = mimetypes.guess_type(uploaded.name)
    mime = mime or getattr(uploaded, 'content_type', None) or 'application/octet-stream'

    # Save original raw file directly without any modification (no cropping, no color change, no compression)
    session.uploaded_file     = uploaded
    session.original_filename = uploaded.name
    session.file_size         = uploaded.size
    session.file_mime         = mime
    session.status            = MobileUploadSession.STATUS_COMPLETED
    session.save()

    return JsonResponse({
        'success':  True,
        'filename': uploaded.name,
        'size':     uploaded.size,
    })


# ── 4. Desktop: poll for completion ───────────────────────────────────────────

@login_required
@require_GET
def check_upload_status(request, token):
    """
    GET /mobile/upload/<token>/status/
    Polled by the desktop every 2 seconds.
    Returns JSON with current session status.
    """
    session = get_object_or_404(MobileUploadSession, token=token, created_by=request.user)

    # Auto-expire
    if session.status == MobileUploadSession.STATUS_PENDING and session.is_expired:
        session.mark_expired()

    response = {
        'status':            session.status,
        'seconds_remaining': session.seconds_remaining,
    }

    if session.status == MobileUploadSession.STATUS_COMPLETED:
        response['filename']  = session.original_filename
        response['file_size'] = session.file_size
        response['file_mime'] = session.file_mime
        # Build a download URL the desktop user can click
        if session.uploaded_file:
            response['file_url'] = request.build_absolute_uri(session.uploaded_file.url)

    return JsonResponse(response)
