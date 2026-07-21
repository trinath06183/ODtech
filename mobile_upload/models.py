"""
mobile_upload/models.py
=======================
Stores short-lived upload sessions used for QR-code-based mobile file uploads.
Each session:
  - Has a unique UUID token (embedded in the QR code URL)
  - Expires after 10 minutes
  - Records the file once the phone uploads it
  - Is polled by the desktop browser every 2 seconds to detect completion
"""

import uuid
import os
from django.db import models
from django.conf import settings
from django.utils import timezone


def mobile_upload_path(instance, filename):
    """Store mobile-uploaded files in media/mobile_uploads/<session_token>/"""
    ext = os.path.splitext(filename)[1].lower()
    safe_name = f"upload{ext}"
    return os.path.join('mobile_uploads', str(instance.token), safe_name)


class MobileUploadSession(models.Model):
    """
    A single QR-code upload session.
    Created on the desktop, consumed by a phone scan.
    """
    STATUS_PENDING   = 'pending'
    STATUS_COMPLETED = 'completed'
    STATUS_EXPIRED   = 'expired'
    STATUS_CHOICES = [
        (STATUS_PENDING,   'Pending'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_EXPIRED,   'Expired'),
    ]

    token       = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    created_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='mobile_upload_sessions',
    )
    created_at  = models.DateTimeField(auto_now_add=True)
    expires_at  = models.DateTimeField()
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    # The uploaded file (populated after phone upload)
    uploaded_file     = models.FileField(upload_to=mobile_upload_path, null=True, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    file_size         = models.PositiveIntegerField(null=True, blank=True)  # bytes
    file_mime         = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name        = 'Mobile Upload Session'
        verbose_name_plural = 'Mobile Upload Sessions'

    def __str__(self):
        return f"Session {str(self.token)[:8]}… — {self.status} (by {self.created_by})"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timezone.timedelta(minutes=10)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def seconds_remaining(self):
        delta = self.expires_at - timezone.now()
        return max(0, int(delta.total_seconds()))

    def mark_expired(self):
        self.status = self.STATUS_EXPIRED
        self.save(update_fields=['status'])
