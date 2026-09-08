"""
HR Admin Registration
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import LeaveType, LeaveAllocation, LeaveRequest, AttendanceRecord, Holiday


@admin.register(LeaveType)
class LeaveTypeAdmin(admin.ModelAdmin):
    list_display  = ('name', 'code', 'default_days', 'is_paid', 'carry_forward', 'is_active')
    list_filter   = ('is_paid', 'is_active', 'carry_forward')
    search_fields = ('name', 'code')


@admin.register(LeaveAllocation)
class LeaveAllocationAdmin(admin.ModelAdmin):
    list_display  = ('user', 'leave_type', 'year', 'days_allocated', 'days_carried_forward')
    list_filter   = ('year', 'leave_type')
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    autocomplete_fields = ('user', 'leave_type')


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display   = ('employee', 'leave_type', 'from_date', 'to_date', 'days_count', 'status', 'reviewed_by')
    list_filter    = ('status', 'leave_type', 'from_date')
    search_fields  = ('employee__username', 'employee__first_name')
    readonly_fields = ('days_count',)
    date_hierarchy = 'from_date'


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display   = ('employee', 'date', 'status', 'check_in', 'check_out', 'marked_by')
    list_filter    = ('status', 'date')
    search_fields  = ('employee__username', 'employee__first_name')
    date_hierarchy = 'date'


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display  = ('name', 'date', 'is_optional')
    list_filter   = ('is_optional',)
    search_fields = ('name',)
