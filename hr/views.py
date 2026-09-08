"""
HR Views
========
Attendance tracking and leave management views.
"""

import calendar
import csv
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum, Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import require_permission
from .forms import (
    AttendanceFilterForm, BulkAttendanceForm,
    HolidayForm, LeaveAllocationForm,
    LeaveRequestForm, LeaveReviewForm,
)
from .models import AttendanceRecord, Holiday, LeaveAllocation, LeaveRequest, LeaveType

User = get_user_model()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _is_hr_admin(user):
    return user.role in ('Admin', 'Managing Director', 'HR') or user.is_superuser


def _get_leave_balance(user, year=None):
    """Return dict of {leave_type: {allocated, used, remaining}}."""
    if year is None:
        year = timezone.now().year
    allocations = LeaveAllocation.objects.filter(user=user, year=year).select_related('leave_type')
    result = {}
    for alloc in allocations:
        used = LeaveRequest.objects.filter(
            employee=user,
            leave_type=alloc.leave_type,
            status=LeaveRequest.STATUS_APPROVED,
            from_date__year=year,
        ).aggregate(total=Sum('days_count'))['total'] or Decimal('0')
        result[alloc.leave_type_id] = {
            'leave_type': alloc.leave_type,
            'allocated': alloc.total_days,
            'used': used,
            'remaining': max(alloc.total_days - Decimal(str(used)), Decimal('0')),
        }
    return result


def _build_calendar(user, year, month):
    """Build a calendar grid for a given user/month."""
    cal = calendar.Calendar(firstweekday=0)  # Monday first
    holidays = set(Holiday.objects.filter(date__year=year, date__month=month).values_list('date', flat=True))
    records  = {
        r.date: r
        for r in AttendanceRecord.objects.filter(employee=user, date__year=year, date__month=month)
    }
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        week_data = []
        for day in week:
            if day.month != month:
                week_data.append({'date': day, 'outside': True, 'record': None, 'is_holiday': False})
                continue
            is_holiday = day in holidays
            is_weekend = day.weekday() == 6  # Only Sunday is offday
            record = records.get(day)
            week_data.append({
                'date': day,
                'outside': False,
                'record': record,
                'is_holiday': is_holiday,
                'is_weekend': is_weekend,
                'is_today': day == date.today(),
            })
        weeks.append(week_data)
    return weeks


# ─── Dashboard ────────────────────────────────────────────────────────────────

@login_required
@require_permission('HR_ATTENDANCE', 'read')
def dashboard(request):
    today = date.today()
    all_active_users = User.objects.filter(is_active=True).order_by('first_name', 'last_name')

    # Today's attendance summary
    today_records = AttendanceRecord.objects.filter(date=today).select_related('employee')
    today_dict = {r.employee_id: r for r in today_records}
    marked_today  = today_records.count()
    present_today = today_records.filter(status__in=['PRESENT', 'WFH', 'HALF_DAY']).count()
    absent_today  = today_records.filter(status='ABSENT').count()

    # Pending leave requests
    pending_leaves = LeaveRequest.objects.filter(status='PENDING').select_related('employee', 'leave_type').order_by('from_date')

    # Recent attendance
    recent_records = AttendanceRecord.objects.filter(
        date__gte=today - timedelta(days=7)
    ).select_related('employee').order_by('-date')[:50]

    # Upcoming holidays
    upcoming_holidays = Holiday.objects.filter(date__gte=today).order_by('date')[:5]

    # Absent employees today (marked absent or not yet marked)
    absent_employees = []
    for user in all_active_users:
        rec = today_dict.get(user.id)
        if not rec or rec.status == 'ABSENT':
            absent_employees.append({'user': user, 'record': rec})

    context = {
        'today': today,
        'all_users': all_active_users,
        'today_dict': today_dict,
        'marked_today': marked_today,
        'total_employees': all_active_users.count(),
        'present_today': present_today,
        'absent_today': absent_today,
        'pending_leaves': pending_leaves,
        'pending_count': pending_leaves.count(),
        'recent_records': recent_records,
        'upcoming_holidays': upcoming_holidays,
        'absent_employees': absent_employees[:10],
        'is_hr_admin': _is_hr_admin(request.user),
    }
    return render(request, 'hr/dashboard.html', context)


# ─── Bulk Attendance Marking ──────────────────────────────────────────────────

@login_required
@require_permission('HR_ATTENDANCE', 'write')
def mark_attendance(request):
    """HR marks attendance for all employees for a given date."""
    selected_date = date.today()
    employees = User.objects.filter(is_active=True).order_by('first_name', 'last_name')

    if request.method == 'POST':
        form = BulkAttendanceForm(request.POST)
        if form.is_valid():
            selected_date = form.cleaned_data['date']
            updated = 0
            for user in employees:
                field_name = f'status_{user.id}'
                notes_field = f'notes_{user.id}'
                check_in_field  = f'check_in_{user.id}'
                check_out_field = f'check_out_{user.id}'
                status = request.POST.get(field_name)
                if not status:
                    continue
                rec, _ = AttendanceRecord.objects.update_or_create(
                    employee=user,
                    date=selected_date,
                    defaults={
                        'status': status,
                        'notes': request.POST.get(notes_field, ''),
                        'check_in': request.POST.get(check_in_field) or None,
                        'check_out': request.POST.get(check_out_field) or None,
                        'marked_by': request.user,
                    }
                )
                updated += 1
            messages.success(request, f"Attendance saved for {updated} employee(s) on {selected_date}.")
            return redirect('hr:mark_attendance')
    else:
        form = BulkAttendanceForm(initial={'date': selected_date})
        if request.GET.get('date'):
            try:
                from datetime import datetime
                selected_date = datetime.strptime(request.GET['date'], '%Y-%m-%d').date()
                form = BulkAttendanceForm(initial={'date': selected_date})
            except ValueError:
                pass

    # Existing records for selected_date
    existing = {r.employee_id: r for r in AttendanceRecord.objects.filter(date=selected_date)}
    holidays = Holiday.objects.filter(date=selected_date)
    is_holiday = holidays.exists()
    is_weekend  = selected_date.weekday() == 6  # Only Sunday is offday

    # Approved leaves on this date
    leaves_on_date = {
        lr.employee_id: lr
        for lr in LeaveRequest.objects.filter(
            status='APPROVED',
            from_date__lte=selected_date,
            to_date__gte=selected_date
        ).select_related('leave_type')
    }

    employees_data = []
    for user in employees:
        rec = existing.get(user.id)
        leave = leaves_on_date.get(user.id)
        employees_data.append({
            'user': user,
            'record': rec,
            'leave': leave,
            'default_status': 'ON_LEAVE' if leave else ('WEEKLY_OFF' if is_weekend else 'PRESENT'),
        })

    context = {
        'form': form,
        'selected_date': selected_date,
        'employees_data': employees_data,
        'is_holiday': is_holiday,
        'holiday_name': holidays.first().name if is_holiday else '',
        'is_weekend': is_weekend,
        'status_choices': AttendanceRecord.STATUS_CHOICES,
    }
    return render(request, 'hr/attendance_mark.html', context)


# ─── Attendance History ───────────────────────────────────────────────────────

@login_required
@require_permission('HR_ATTENDANCE', 'read')
def attendance_history(request, user_id=None):
    """Monthly calendar view of attendance for a single employee."""
    today = date.today()
    year  = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))

    # Which employee to view
    if user_id and _is_hr_admin(request.user):
        employee = get_object_or_404(User, id=user_id)
    else:
        employee = request.user

    weeks = _build_calendar(employee, year, month)

    # Summary for this month
    records = AttendanceRecord.objects.filter(employee=employee, date__year=year, date__month=month)
    summary = records.values('status').annotate(count=Count('status'))
    summary_dict = {s['status']: s['count'] for s in summary}

    # Leave balance
    leave_balance = _get_leave_balance(employee, year)

    # Leave requests for this month
    leave_requests = LeaveRequest.objects.filter(
        employee=employee,
        from_date__year=year,
        from_date__month=month
    ).select_related('leave_type').order_by('from_date')

    all_employees = User.objects.filter(is_active=True).order_by('first_name') if _is_hr_admin(request.user) else []

    month_name  = calendar.month_name[month]
    prev_month  = date(year, month, 1) - timedelta(days=1)
    next_date   = date(year, month, 28) + timedelta(days=4)
    next_month  = next_date.replace(day=1)

    context = {
        'employee': employee,
        'year': year,
        'month': month,
        'month_name': month_name,
        'weeks': weeks,
        'summary': summary_dict,
        'leave_balance': leave_balance,
        'leave_requests': leave_requests,
        'all_employees': all_employees,
        'prev_year': prev_month.year,
        'prev_month': prev_month.month,
        'next_year': next_month.year,
        'next_month': next_month.month,
        'status_choices': AttendanceRecord.STATUS_CHOICES,
        'is_hr_admin': _is_hr_admin(request.user),
    }
    return render(request, 'hr/attendance_history.html', context)


# ─── Leave Application ────────────────────────────────────────────────────────

@login_required
@require_permission('HR_ATTENDANCE', 'read')
def apply_leave(request):
    """Employee applies for leave."""
    year = timezone.now().year
    leave_balance = _get_leave_balance(request.user, year)
    my_requests = LeaveRequest.objects.filter(employee=request.user).select_related('leave_type').order_by('-from_date')[:20]

    if request.method == 'POST':
        form = LeaveRequestForm(request.POST, request.FILES)
        if form.is_valid():
            leave_req = form.save(commit=False)
            leave_req.employee = request.user
            leave_type = leave_req.leave_type
            # Quota check for paid leaves that have allocations
            if leave_type.requires_approval is False:
                pass  # LOP — no quota needed
            balance = leave_balance.get(leave_type.id, {})
            if balance and leave_type.default_days > 0:
                remaining = balance.get('remaining', 0)
                if Decimal(str(leave_req.calculate_days())) > remaining:
                    messages.warning(request, f"You only have {remaining} day(s) of {leave_type.name} remaining.")
            leave_req.save()
            messages.success(request, f"Leave request submitted for {leave_req.from_date} to {leave_req.to_date}.")
            return redirect('hr:apply_leave')
    else:
        form = LeaveRequestForm()

    context = {
        'form': form,
        'leave_balance': leave_balance,
        'my_requests': my_requests,
    }
    return render(request, 'hr/leave_apply.html', context)


@login_required
@require_permission('HR_ATTENDANCE', 'read')
def cancel_leave(request, leave_id):
    """Employee cancels own pending leave request."""
    leave_req = get_object_or_404(LeaveRequest, id=leave_id, employee=request.user)
    if leave_req.status == 'PENDING':
        leave_req.status = 'CANCELLED'
        leave_req.save()
        messages.success(request, "Leave request cancelled.")
    else:
        messages.error(request, "Only pending requests can be cancelled.")
    return redirect('hr:apply_leave')


# ─── Leave Requests (HR View) ─────────────────────────────────────────────────

@login_required
@require_permission('HR_ATTENDANCE', 'write')
def leave_requests(request):
    """HR/Admin list and approve/reject all leave requests."""
    status_filter = request.GET.get('status', 'PENDING')
    employee_filter = request.GET.get('employee', '')

    qs = LeaveRequest.objects.select_related('employee', 'leave_type', 'reviewed_by').order_by('-from_date')
    if status_filter:
        qs = qs.filter(status=status_filter)
    if employee_filter:
        qs = qs.filter(
            Q(employee__first_name__icontains=employee_filter) |
            Q(employee__last_name__icontains=employee_filter) |
            Q(employee__username__icontains=employee_filter)
        )

    all_employees = User.objects.filter(is_active=True).order_by('first_name')

    context = {
        'leave_requests': qs[:100],
        'status_filter': status_filter,
        'employee_filter': employee_filter,
        'all_employees': all_employees,
        'status_choices': LeaveRequest.STATUS_CHOICES,
    }
    return render(request, 'hr/leave_requests.html', context)


@login_required
@require_permission('HR_ATTENDANCE', 'write')
def review_leave(request, leave_id):
    """HR approves or rejects a leave request."""
    leave_req = get_object_or_404(LeaveRequest, id=leave_id)

    if request.method == 'POST':
        form = LeaveReviewForm(request.POST, instance=leave_req)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.reviewed_by = request.user
            obj.reviewed_at = timezone.now()
            obj.save()

            # If approved, mark attendance records as ON_LEAVE for each day
            if obj.status == 'APPROVED':
                current = obj.from_date
                while current <= obj.to_date:
                    if current.weekday() != 6:  # Monday to Saturday are working days
                        AttendanceRecord.objects.update_or_create(
                            employee=obj.employee,
                            date=current,
                            defaults={
                                'status': 'ON_LEAVE',
                                'leave_request': obj,
                                'marked_by': request.user,
                            }
                        )
                    current += timedelta(days=1)

            messages.success(request, f"Leave request {obj.get_status_display()} for {obj.employee.get_full_name() or obj.employee.username}.")
            return redirect('hr:leave_requests')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = LeaveReviewForm(instance=leave_req)

    balance = _get_leave_balance(leave_req.employee).get(leave_req.leave_type_id, {})
    context = {
        'leave_req': leave_req,
        'form': form,
        'balance': balance,
    }
    return render(request, 'hr/leave_review.html', context)


# ─── Leave Balance Summary ────────────────────────────────────────────────────

@login_required
@require_permission('HR_ATTENDANCE', 'read')
def leave_balance(request):
    """Leave balance summary for all employees."""
    year = int(request.GET.get('year', timezone.now().year))
    employees = User.objects.filter(is_active=True).order_by('first_name', 'last_name')
    leave_types = LeaveType.objects.filter(is_active=True)

    data = []
    for user in employees:
        balances = _get_leave_balance(user, year)
        data.append({'user': user, 'balances': balances})

    context = {
        'data': data,
        'leave_types': leave_types,
        'year': year,
        'years': range(2023, timezone.now().year + 2),
        'is_hr_admin': _is_hr_admin(request.user),
    }
    return render(request, 'hr/leave_balance.html', context)


# ─── Monthly Attendance Report ────────────────────────────────────────────────

@login_required
@require_permission('HR_ATTENDANCE', 'read')
def attendance_report(request):
    """Monthly attendance report with CSV download."""
    today = date.today()
    form  = AttendanceFilterForm(request.GET or None)
    year  = today.year
    month = today.month
    employee_id = None

    if form.is_valid() or not request.GET:
        if form.is_valid():
            year  = int(form.cleaned_data['year'])
            month = int(form.cleaned_data['month'])
            emp   = form.cleaned_data.get('employee')
            employee_id = emp.id if emp else None

    employees = User.objects.filter(is_active=True).order_by('first_name', 'last_name')
    if employee_id:
        employees = employees.filter(id=employee_id)

    holidays = set(Holiday.objects.filter(date__year=year, date__month=month).values_list('date', flat=True))
    _, days_in_month = calendar.monthrange(year, month)
    all_dates = [date(year, month, d) for d in range(1, days_in_month + 1)]
    working_dates = [d for d in all_dates if d.weekday() != 6 and d not in holidays]

    records = AttendanceRecord.objects.filter(
        date__year=year, date__month=month
    )
    if employee_id:
        records = records.filter(employee_id=employee_id)

    records_map = {}
    for r in records.select_related('employee'):
        records_map.setdefault(r.employee_id, {})[r.date] = r

    report_data = []
    for user in employees:
        emp_records = records_map.get(user.id, {})
        present = sum(1 for d in working_dates if emp_records.get(d) and emp_records[d].status in ['PRESENT', 'WFH'])
        half_day = sum(1 for d in working_dates if emp_records.get(d) and emp_records[d].status == 'HALF_DAY')
        on_leave = sum(1 for d in working_dates if emp_records.get(d) and emp_records[d].status == 'ON_LEAVE')
        absent   = sum(1 for d in working_dates if not emp_records.get(d) or emp_records[d].status == 'ABSENT')
        report_data.append({
            'user': user,
            'records': emp_records,
            'working_days': len(working_dates),
            'present': present,
            'half_day': half_day,
            'on_leave': on_leave,
            'absent': absent,
        })

    # CSV download
    if request.GET.get('download') == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="attendance_{year}_{month:02d}.csv"'
        writer = csv.writer(response)
        header = ['Employee', 'Working Days'] + [d.strftime('%d %a') for d in all_dates] + ['Present', 'Half Day', 'On Leave', 'Absent']
        writer.writerow(header)
        for row in report_data:
            cells = []
            for d in all_dates:
                r = row['records'].get(d, None)
                if r:
                    cells.append(r.get_status_display())
                elif d.weekday() == 6:
                    cells.append('Weekly Off')
                elif d in holidays:
                    cells.append('Holiday')
                else:
                    cells.append('—')
            writer.writerow([
                str(row['user']),
                row['working_days'],
            ] + cells + [row['present'], row['half_day'], row['on_leave'], row['absent']])
        return response

    context = {
        'form': form,
        'report_data': report_data,
        'working_dates': working_dates,
        'all_dates': all_dates,
        'year': year,
        'month': month,
        'month_name': calendar.month_name[month],
        'holidays': holidays,
        'is_hr_admin': _is_hr_admin(request.user),
        'employee_id': employee_id,
    }
    return render(request, 'hr/report.html', context)


# ─── Leave Allocations ────────────────────────────────────────────────────────

@login_required
@require_permission('HR_ATTENDANCE', 'write')
def manage_allocations(request):
    """HR manages leave allocations for employees."""
    year = int(request.GET.get('year', timezone.now().year))
    allocations = LeaveAllocation.objects.filter(year=year).select_related('user', 'leave_type').order_by('user__first_name')

    if request.method == 'POST':
        form = LeaveAllocationForm(request.POST)
        if form.is_valid():
            alloc = form.save(commit=False)
            alloc.created_by = request.user
            alloc.save()
            messages.success(request, "Leave allocation saved.")
            return redirect(f'hr:manage_allocations')
    else:
        form = LeaveAllocationForm(initial={'year': year})

    leave_types = LeaveType.objects.filter(is_active=True)
    employees   = User.objects.filter(is_active=True).order_by('first_name')

    context = {
        'form': form,
        'allocations': allocations,
        'year': year,
        'years': range(2023, timezone.now().year + 2),
        'leave_types': leave_types,
        'employees': employees,
    }
    return render(request, 'hr/manage_allocations.html', context)


# ─── Holidays ─────────────────────────────────────────────────────────────────

@login_required
@require_permission('HR_ATTENDANCE', 'write')
def manage_holidays(request):
    """HR manages office holidays."""
    year = int(request.GET.get('year', timezone.now().year))
    holidays = Holiday.objects.filter(date__year=year).order_by('date')

    if request.method == 'POST':
        form = HolidayForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Holiday added.")
            return redirect('hr:manage_holidays')
    else:
        form = HolidayForm()

    context = {
        'form': form,
        'holidays': holidays,
        'year': year,
        'years': range(2023, timezone.now().year + 2),
    }
    return render(request, 'hr/manage_holidays.html', context)


@login_required
@require_permission('HR_ATTENDANCE', 'write')
def delete_holiday(request, holiday_id):
    holiday = get_object_or_404(Holiday, id=holiday_id)
    holiday.delete()
    messages.success(request, "Holiday deleted.")
    return redirect('hr:manage_holidays')


# ─── My Attendance (self-view) ─────────────────────────────────────────────────

@login_required
@require_permission('HR_ATTENDANCE', 'read')
def my_attendance(request):
    """Shortcut: view own attendance history."""
    return attendance_history(request, user_id=None)
