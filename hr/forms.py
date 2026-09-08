from django import forms
from django.contrib.auth import get_user_model
from .models import LeaveRequest, AttendanceRecord, LeaveType, LeaveAllocation, Holiday

User = get_user_model()


class LeaveRequestForm(forms.ModelForm):
    """Employee self-service leave application form."""

    class Meta:
        model = LeaveRequest
        fields = ['leave_type', 'from_date', 'to_date', 'session', 'reason', 'attachment']
        widgets = {
            'leave_type': forms.Select(attrs={'class': 'w-full rounded-xl border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:ring-2 focus:ring-violet-500'}),
            'from_date':  forms.DateInput(attrs={'type': 'date', 'class': 'w-full rounded-xl border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:ring-2 focus:ring-violet-500'}),
            'to_date':    forms.DateInput(attrs={'type': 'date', 'class': 'w-full rounded-xl border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:ring-2 focus:ring-violet-500'}),
            'session':    forms.Select(attrs={'class': 'w-full rounded-xl border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:ring-2 focus:ring-violet-500'}),
            'reason':     forms.Textarea(attrs={'rows': 3, 'class': 'w-full rounded-xl border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:ring-2 focus:ring-violet-500', 'placeholder': 'Reason for leave...'}),
            'attachment': forms.FileInput(attrs={'class': 'w-full rounded-xl border-slate-200 bg-slate-50 px-3 py-2 text-sm'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['leave_type'].queryset = LeaveType.objects.filter(is_active=True)
        self.fields['attachment'].required = False

    def clean(self):
        cleaned_data = super().clean()
        from_date = cleaned_data.get('from_date')
        to_date   = cleaned_data.get('to_date')
        if from_date and to_date and to_date < from_date:
            raise forms.ValidationError("'To Date' cannot be before 'From Date'.")
        return cleaned_data


class LeaveReviewForm(forms.ModelForm):
    """HR/Admin approval/rejection form."""

    class Meta:
        model = LeaveRequest
        fields = ['status', 'reviewer_note']
        widgets = {
            'status':        forms.Select(attrs={'class': 'w-full rounded-xl border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:ring-2 focus:ring-violet-500'}),
            'reviewer_note': forms.Textarea(attrs={'rows': 2, 'class': 'w-full rounded-xl border-slate-200 bg-slate-50 px-3 py-2 text-sm focus:ring-2 focus:ring-violet-500', 'placeholder': 'Optional note to employee...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only allow APPROVED or REJECTED
        self.fields['status'].choices = [
            ('APPROVED', 'Approve'),
            ('REJECTED', 'Reject'),
        ]


class BulkAttendanceForm(forms.Form):
    """Form for HR to mark attendance for all employees on a specific date."""
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'rounded-xl border-slate-200 bg-white px-4 py-2 text-sm shadow-sm focus:ring-2 focus:ring-violet-500'}),
        initial=None
    )


class LeaveAllocationForm(forms.ModelForm):
    class Meta:
        model  = LeaveAllocation
        fields = ['user', 'leave_type', 'year', 'days_allocated', 'days_carried_forward']
        widgets = {
            'user':       forms.Select(attrs={'class': 'w-full rounded-xl border-slate-200 bg-slate-50 px-3 py-2 text-sm'}),
            'leave_type': forms.Select(attrs={'class': 'w-full rounded-xl border-slate-200 bg-slate-50 px-3 py-2 text-sm'}),
            'year':       forms.NumberInput(attrs={'class': 'w-full rounded-xl border-slate-200 bg-slate-50 px-3 py-2 text-sm'}),
            'days_allocated':       forms.NumberInput(attrs={'class': 'w-full rounded-xl border-slate-200 bg-slate-50 px-3 py-2 text-sm', 'step': '0.5'}),
            'days_carried_forward': forms.NumberInput(attrs={'class': 'w-full rounded-xl border-slate-200 bg-slate-50 px-3 py-2 text-sm', 'step': '0.5'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = User.objects.filter(is_active=True).order_by('empid', 'first_name')
        self.fields['user'].label_from_instance = lambda obj: (
            f"{obj.empid or obj.username} — {obj.get_full_name()}" if obj.get_full_name() else (obj.empid or obj.username)
        )


class HolidayForm(forms.ModelForm):
    class Meta:
        model  = Holiday
        fields = ['name', 'date', 'is_optional']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full rounded-xl border-slate-200 bg-slate-50 px-3 py-2 text-sm'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full rounded-xl border-slate-200 bg-slate-50 px-3 py-2 text-sm'}),
        }


class AttendanceFilterForm(forms.Form):
    """Filter attendance history view."""
    MONTH_CHOICES = [(i, m) for i, m in enumerate([
        'January','February','March','April','May','June',
        'July','August','September','October','November','December'
    ], 1)]

    year  = forms.IntegerField(min_value=2020, max_value=2100,
        widget=forms.NumberInput(attrs={'class': 'rounded-xl border-slate-200 px-3 py-2 text-sm w-28'}))
    month = forms.ChoiceField(choices=MONTH_CHOICES,
        widget=forms.Select(attrs={'class': 'rounded-xl border-slate-200 px-3 py-2 text-sm'}))
    employee = forms.ModelChoiceField(queryset=User.objects.none(), required=False, empty_label='All Employees',
        widget=forms.Select(attrs={'class': 'rounded-xl border-slate-200 px-3 py-2 text-sm'}))

    def __init__(self, *args, **kwargs):
        from django.utils import timezone as tz
        super().__init__(*args, **kwargs)
        now = tz.now()
        if not self.data.get('year'):
            self.fields['year'].initial = now.year
        if not self.data.get('month'):
            self.fields['month'].initial = now.month
        self.fields['employee'].queryset = User.objects.filter(is_active=True).order_by('empid', 'first_name')
        self.fields['employee'].label_from_instance = lambda obj: (
            f"{obj.empid or obj.username} — {obj.get_full_name()}" if obj.get_full_name() else (obj.empid or obj.username)
        )
