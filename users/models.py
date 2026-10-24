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

    def __str__(self):
        code = self.empid or self.username
        full_name = self.get_full_name().strip()
        if full_name:
            return f"{code} — {full_name}"
        return code

    @property
    def can_view_fixed_costs(self):
        """
        Returns True if user is authorized to view, manage, and create Fixed Cost expenses.
        Authorized roles: Admin, Managing Director, Director, Accounts, Accountant, HR,
        as well as superusers and staff.
        """
        if self.is_superuser or self.is_staff:
            return True
        return self.role in ['Admin', 'Managing Director', 'Director', 'Accounts', 'Accountant', 'HR']

    @property
    def can_view_confidential_expenses(self):
        """Alias for can_view_fixed_costs."""
        return self.can_view_fixed_costs

    @property
    def can_view_company_overview(self):
        """
        Returns True if user is authorized to view Company Overview Dashboard.
        Authorized roles: Admin, Managing Director, Director, Accounts, Accountant, HR,
        as well as superusers and staff.
        """
        if self.is_superuser or self.is_staff:
            return True
        return self.role in ['Admin', 'Managing Director', 'Director', 'Accounts', 'Accountant', 'HR']

    @property
    def is_admin_or_superuser(self):
        """
        Returns True if user is a superuser, staff, or holds an administrative role
        (Admin, Managing Director, Director).
        """
        if self.is_superuser or self.is_staff:
            return True
        return self.role in ['Admin', 'Managing Director', 'Director']

    def has_section_perm(self, section, access_type='read'):
        """
        Check if user has permission for a specific section.
        Admins and superusers have full access to all sections.
        USERS section is strictly restricted to Admin and superusers only.
        Managing Directors bypass all checks except USERS.
        access_type can be 'read' or 'write'.
        """
        if self.is_superuser or self.role == 'Admin':
            return True

        # User Management section is strictly Admin only
        if section == 'USERS':
            return False

        if self.role == 'Managing Director':
            return True

        # HR role has full access to HR_ATTENDANCE
        if self.role == 'HR' and section == 'HR_ATTENDANCE':
            return True

        # All authenticated employees can view HR & Attendance (apply leave, view personal history)
        if section == 'HR_ATTENDANCE' and access_type == 'read':
            return True
            
        perm = self.section_permissions.filter(section=section).first()
        if not perm:
            return False
            
        if access_type == 'write':
            return perm.can_write
        return perm.can_read


class AppSection(models.TextChoices):
    DASHBOARD = 'DASHBOARD', 'Dashboard'
    USERS = 'USERS', 'User Management'
    CONTACTS = 'CONTACTS', 'Contacts (Clients/Vendors)'
    INVENTORY = 'INVENTORY', 'Inventory & Warranty'
    EDMS = 'EDMS', 'Document Management (EDMS)'
    PAYMENTS = 'PAYMENTS', 'Payments & Expenses'
    REPORTING = 'REPORTING', 'Reporting'
    TRACKER = 'TRACKER', 'Manufacturing Tracker'
    DOCUMENTS = 'DOCUMENTS', 'Invoices & Estimates'
    HR_ATTENDANCE = 'HR_ATTENDANCE', 'HR & Attendance'


class UserSectionPermission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='section_permissions')
    section = models.CharField(max_length=50, choices=AppSection.choices)
    can_read = models.BooleanField(default=False)
    can_write = models.BooleanField(default=False)

    class Meta:
        unique_together = ('user', 'section')
        verbose_name = 'Section Permission'
        verbose_name_plural = 'Section Permissions'

    def __str__(self):
        return f"{self.user.username} - {self.get_section_display()}"


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
