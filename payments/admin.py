from django.contrib import admin
from django.utils import timezone
from .models import Payment, Expense


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('contact', 'amount', 'payment_mode', 'date', 'reference_number')
    search_fields = ('contact__name', 'reference_number')
    list_filter = ('payment_mode', 'date')


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = (
        'formatted_id_display',
        'title',
        'employee_code',
        'expense_type',
        'amount',
        'date',
        'submitted_by',
        'status',
        'is_paid',
        'approved_by',
    )
    list_filter = ('status', 'is_paid', 'expense_type', 'date')
    search_fields = (
        'title',
        'employee_code',
        'submitted_by__username',
        'submitted_by__first_name',
        'submitted_by__last_name',
        'submitted_by__empid',
        'notes',
    )
    list_editable = ('status', 'is_paid')
    readonly_fields = ('created_at', 'updated_at', 'approved_at', 'paid_at')
    ordering = ('-date', '-id')
    actions = ['approve_expenses', 'reject_expenses', 'mark_as_paid', 'reset_to_pending']

    @admin.display(description="Expense ID", ordering="id")
    def formatted_id_display(self, obj):
        return obj.formatted_id

    def save_model(self, request, obj, form, change):
        if obj.status == 'Approved' and not obj.approved_by:
            obj.approved_by = request.user
            obj.approved_at = timezone.now()
        elif obj.status == 'Pending':
            obj.approved_by = None
            obj.approved_at = None

        if obj.is_paid and not obj.paid_at:
            obj.paid_at = timezone.now()
        elif not obj.is_paid:
            obj.paid_at = None

        super().save_model(request, obj, form, change)

    @admin.action(description="Approve selected expenses")
    def approve_expenses(self, request, queryset):
        count = queryset.update(
            status='Approved',
            approved_by=request.user,
            approved_at=timezone.now(),
        )
        self.message_user(request, f"Successfully approved {count} expense(s).")

    @admin.action(description="Reject selected expenses")
    def reject_expenses(self, request, queryset):
        count = queryset.update(
            status='Rejected',
            approved_by=request.user,
            approved_at=timezone.now(),
        )
        self.message_user(request, f"Successfully rejected {count} expense(s).")

    @admin.action(description="Mark selected expenses as Paid")
    def mark_as_paid(self, request, queryset):
        count = queryset.update(
            is_paid=True,
            paid_at=timezone.now(),
        )
        self.message_user(request, f"Successfully marked {count} expense(s) as Paid.")

    @admin.action(description="Reset selected expenses to Pending")
    def reset_to_pending(self, request, queryset):
        count = queryset.update(
            status='Pending',
            approved_by=None,
            approved_at=None,
        )
        self.message_user(request, f"Successfully reset {count} expense(s) to Pending.")
