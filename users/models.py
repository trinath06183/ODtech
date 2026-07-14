import random
import string
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.conf import settings
from core.models import TimeStampedModel


class User(AbstractUser, TimeStampedModel):
    ROLE_CHOICES = (
        # ── EDMS / Enterprise Roles ───────────────────────────────────────────
        ('Managing Director', 'Managing Director'),
        ('Director', 'Director'),
        ('Admin', 'Admin'),
        ('Purchase', 'Purchase'),
        ('Accounts', 'Accounts'),
        ('Tender', 'Tender'),
        ('HR', 'HR'),
        ('Engineering', 'Engineering'),
        ('Project', 'Project'),
        ('Viewer', 'Viewer'),
        # ── Legacy roles (kept for backward compatibility) ────────────────────
        ('Accountant', 'Accountant'),
        ('Staff', 'Staff'),
    )
    role = models.CharField(max_length=30, choices=ROLE_CHOICES, default='Staff')
    designation = models.CharField(max_length=100, blank=True, null=True)
    empid = models.CharField(max_length=50, unique=True, blank=True, null=True)
    is_email_verified = models.BooleanField(default=False)
    is_onboarded = models.BooleanField(default=True)


class OTPToken(models.Model):
    """Stores a short-lived 6-digit OTP for password reset verification."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='otp_tokens'
    )
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'OTP Token'
        verbose_name_plural = 'OTP Tokens'

    def __str__(self):
        return f"OTP for {self.user.username} ({'used' if self.used else 'active'})"

    @classmethod
    def generate_for_user(cls, user):
        """Invalidate old tokens and create a fresh OTP for this user."""
        # Mark all previous tokens as used
        cls.objects.filter(user=user, used=False).update(used=True)

        expiry_minutes = getattr(settings, 'OTP_EXPIRY_MINUTES', 10)
        otp_code = ''.join(random.choices(string.digits, k=6))
        token = cls.objects.create(
            user=user,
            otp=otp_code,
            expires_at=timezone.now() + timezone.timedelta(minutes=expiry_minutes),
        )
        return token

    def is_valid(self):
        """Returns True if the OTP has not been used and has not expired."""
        return not self.used and timezone.now() <= self.expires_at
