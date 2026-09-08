"""
HR & Attendance Models
======================
Models for employee attendance tracking, leave management, and HR reporting.

Models:
  - LeaveType          — Configurable leave types (CL, EL, Medical, LOP, etc.)
  - LeaveAllocation    — Annual leave quota per employee per type per year
  - LeaveRequest       — Employee leave applications with approval workflow
  - AttendanceRecord   — Daily attendance status per employee
  - Holiday            — Office holidays (skipped in attendance/leave counting)
"""

import uuid
from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from core.models import TimeStampedModel

User = get_user_model()


# ─── Leave Type ───────────────────────────────────────────────────────────────

class LeaveType(TimeStampedModel):
    """Configurable leave categories managed by HR."""

    name = models.CharField(max_length=100, unique=True, help_text="E.g. Casual Leave, Medical Leave")
    code = models.CharField(max_length=10, unique=True, help_text="Short code, e.g. CL, EL, ML")
    default_days = models.PositiveSmallIntegerField(default=0, help_text="Default annual allocation (0 = unlimited / LOP)")
    is_paid = models.BooleanField(default=True, help_text="Is this a paid leave?")
    requires_approval = models.BooleanField(default=True)
    carry_forward = models.BooleanField(default=False, help_text="Unused days roll over to next year")
    max_carry_forward_days = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    color = models.CharField(max_length=20, default='#6366f1', help_text="Badge colour (hex)")

    class Meta:
        ordering = ['name']
        verbose_name = 'Leave Type'
        verbose_name_plural = 'Leave Types'

    def __str__(self):
        return f"{self.name} ({self.code})"


# ─── Leave Allocation ─────────────────────────────────────────────────────────

class LeaveAllocation(TimeStampedModel):
    """Annual leave balance allocated to an employee for a specific leave type."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='leave_allocations')
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, related_name='allocations')
    year = models.PositiveSmallIntegerField(help_text="Calendar year, e.g. 2026")
    days_allocated = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    days_carried_forward = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='leave_allocations_created'
    )

    class Meta:
        unique_together = ('user', 'leave_type', 'year')
        ordering = ['-year', 'user__first_name']
        verbose_name = 'Leave Allocation'

    @property
    def total_days(self):
        return self.days_allocated + self.days_carried_forward

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} — {self.leave_type.code} {self.year}"


# ─── Leave Request ────────────────────────────────────────────────────────────

class LeaveRequest(TimeStampedModel):
    """An employee's leave application with approval workflow."""

    STATUS_PENDING  = 'PENDING'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_CHOICES = [
        (STATUS_PENDING,   'Pending'),
        (STATUS_APPROVED,  'Approved'),
        (STATUS_REJECTED,  'Rejected'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    SESSION_FULL      = 'FULL'
    SESSION_FIRST     = 'FIRST_HALF'
    SESSION_SECOND    = 'SECOND_HALF'
    SESSION_CHOICES = [
        (SESSION_FULL,   'Full Day'),
        (SESSION_FIRST,  'First Half'),
        (SESSION_SECOND, 'Second Half'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='leave_requests'
    )
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, related_name='requests')
    from_date  = models.DateField()
    to_date    = models.DateField()
    session    = models.CharField(max_length=20, choices=SESSION_CHOICES, default=SESSION_FULL)
    days_count = models.DecimalField(max_digits=5, decimal_places=1, default=0, help_text="Auto-calculated working days")
    reason     = models.TextField(help_text="Reason for leave")
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)

    # Approval
    reviewed_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='leave_reviews'
    )
    reviewed_at   = models.DateTimeField(null=True, blank=True)
    reviewer_note = models.TextField(blank=True)

    # Supporting document (optional)
    attachment = models.FileField(upload_to='hr/leave_attachments/', null=True, blank=True)

    class Meta:
        ordering = ['-from_date']
        verbose_name = 'Leave Request'
        verbose_name_plural = 'Leave Requests'

    def __str__(self):
        name = self.employee.get_full_name() or self.employee.username
        return f"{name} — {self.leave_type.code} ({self.from_date} to {self.to_date})"

    def calculate_days(self):
        """Calculate working days between from_date and to_date (excludes weekends)."""
        from datetime import timedelta
        if not self.from_date or not self.to_date:
            return 0
        delta = (self.to_date - self.from_date).days + 1
        working = sum(
            1 for i in range(delta)
            if (self.from_date + timedelta(days=i)).weekday() < 6  # Mon-Sat are working days; Sunday is off
        )
        if self.session in [self.SESSION_FIRST, self.SESSION_SECOND]:
            working = max(working - 0.5, 0.5)
        return working

    def save(self, *args, **kwargs):
        if self.from_date and self.to_date:
            self.days_count = self.calculate_days()
        super().save(*args, **kwargs)

    def days_used_for_type(self):
        """Total approved days used this year for this leave type by this employee."""
        from django.db.models import Sum
        year = self.from_date.year if self.from_date else timezone.now().year
        total = LeaveRequest.objects.filter(
            employee=self.employee,
            leave_type=self.leave_type,
            status=self.STATUS_APPROVED,
            from_date__year=year
        ).exclude(pk=self.pk).aggregate(total=Sum('days_count'))['total'] or 0
        return total


# ─── Attendance Record ────────────────────────────────────────────────────────

class AttendanceRecord(models.Model):
    """One attendance record per employee per working day."""

    STATUS_PRESENT   = 'PRESENT'
    STATUS_ABSENT    = 'ABSENT'
    STATUS_HALFDAY   = 'HALF_DAY'
    STATUS_WFH       = 'WFH'
    STATUS_ON_LEAVE  = 'ON_LEAVE'
    STATUS_HOLIDAY   = 'HOLIDAY'
    STATUS_WEEKLY_OFF = 'WEEKLY_OFF'

    STATUS_CHOICES = [
        (STATUS_PRESENT,    'Present'),
        (STATUS_ABSENT,     'Absent'),
        (STATUS_HALFDAY,    'Half Day'),
        (STATUS_WFH,        'Work From Home'),
        (STATUS_ON_LEAVE,   'On Leave'),
        (STATUS_HOLIDAY,    'Holiday'),
        (STATUS_WEEKLY_OFF, 'Weekly Off'),
    ]

    STATUS_COLORS = {
        STATUS_PRESENT:    'bg-green-100 text-green-700 border-green-200',
        STATUS_ABSENT:     'bg-red-100 text-red-700 border-red-200',
        STATUS_HALFDAY:    'bg-yellow-100 text-yellow-700 border-yellow-200',
        STATUS_WFH:        'bg-blue-100 text-blue-700 border-blue-200',
        STATUS_ON_LEAVE:   'bg-purple-100 text-purple-700 border-purple-200',
        STATUS_HOLIDAY:    'bg-gray-100 text-gray-500 border-gray-200',
        STATUS_WEEKLY_OFF: 'bg-slate-100 text-slate-400 border-slate-200',
    }

    employee   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attendance_records')
    date       = models.DateField(db_index=True)
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PRESENT, db_index=True)
    check_in   = models.TimeField(null=True, blank=True)
    check_out  = models.TimeField(null=True, blank=True)
    notes      = models.TextField(blank=True)
    leave_request = models.ForeignKey(
        LeaveRequest, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='attendance_records', help_text="Linked leave request if status=ON_LEAVE"
    )
    marked_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='attendance_marked'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('employee', 'date')
        ordering = ['-date', 'employee__first_name']
        verbose_name = 'Attendance Record'
        verbose_name_plural = 'Attendance Records'

    def __str__(self):
        name = self.employee.get_full_name() or self.employee.username
        return f"{name} — {self.date} — {self.get_status_display()}"

    @property
    def status_badge_class(self):
        return self.STATUS_COLORS.get(self.status, 'bg-gray-100 text-gray-700')

    @property
    def is_working_day(self):
        return self.status in [self.STATUS_PRESENT, self.STATUS_HALFDAY, self.STATUS_WFH]


# ─── Holiday ──────────────────────────────────────────────────────────────────

class Holiday(models.Model):
    """Office holidays — skipped in leave and attendance counting."""

    name       = models.CharField(max_length=200)
    date       = models.DateField(unique=True, db_index=True)
    is_optional = models.BooleanField(default=False, help_text="Optional/restricted holiday")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date']
        verbose_name = 'Holiday'
        verbose_name_plural = 'Holidays'

    def __str__(self):
        return f"{self.name} ({self.date})"
