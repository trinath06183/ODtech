from django.db import models
from core.models import TimeStampedModel
from contacts.models import Contact

class Payment(TimeStampedModel):
    PAYMENT_MODES = (
        ('Cash', 'Cash'),
        ('Bank Transfer', 'Bank Transfer'),
        ('Cheque', 'Cheque'),
        ('Credit Card', 'Credit Card'),
        ('UPI', 'UPI'),
    )
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='payments')
    document_ref = models.CharField(max_length=100, blank=True, null=True, help_text="Reference invoice/document number")
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODES)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    date = models.DateField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    @property
    def linked_document(self):
        if not self.document_ref:
            return None
        from documents.models import Document
        return Document.objects.filter(number=self.document_ref).first()

    class Meta:
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['contact', 'date']),
            models.Index(fields=['document_ref']),
            models.Index(fields=['payment_mode']),
        ]

    def __str__(self):
        return f"{self.contact.name} - {self.amount} ({self.date})"

from django.contrib.auth import get_user_model
User = get_user_model()

def user_can_view_fixed_costs(user):
    """
    Returns True if user has permission to view, filter, export, and create Fixed Cost / confidential expenses.
    Authorized: Superusers, Staff, and users with roles:
    'Admin', 'Managing Director', 'Director', 'Accounts', 'Accountant', 'HR'.
    """
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        return True
    return getattr(user, 'role', '') in ['Admin', 'Managing Director', 'Director', 'Accounts', 'Accountant', 'HR']

user_can_view_confidential_expenses = user_can_view_fixed_costs


class Expense(TimeStampedModel):
    DAILY_EXPENSES = (
        ('Petrol and Diesel', 'Petrol and Diesel'),
        ('Travel', 'Travel'),
        ('Hotel', 'Hotel'),
        ('Food Expenses', 'Food Expenses'),
        ('Office stationary', 'Office stationary'),
        ('Courier expenses', 'Courier expenses'),
        ('Transportation Payment', 'Transportation Payment'),
        ('Marketing Expenses', 'Marketing Expenses'),
        ('Customer Delight', 'Customer Delight'),
        ('Other Daily', 'Other'),
    )
    FIXED_COSTS = (
        ('Staff salary', 'Staff salary'),
        ('Office rent', 'Office rent'),
        ('OFC rent', 'OFC rent'),
        ('Electricity bill', 'Electricity bill'),
        ('Internet Bill', 'Internet Bill'),
        ('Google workspace', 'Google workspace'),
        ('Website and hosting cost', 'Website and hosting cost'),
        ('Other Fixed', 'Other'),
    )
    EXPENSE_TYPES = (
        ('Daily Expenses', DAILY_EXPENSES),
        ('Fixed Cost', FIXED_COSTS),
    )

    CONFIDENTIAL_KEYWORDS = [
        'office rent',
        'ofc rent',
        'staff salary',
        'salary',
        'salaries',
        'electricity bill',
        'electricity bills',
        'electric bill',
        'power bill',
        'internet bill',
        'google workspace',
        'hosting cost',
        'website and hosting',
    ]

    @classmethod
    def get_fixed_cost_categories(cls):
        """Returns list of category strings that are classified as Fixed Cost / Confidential."""
        categories = [c[0] for c in cls.FIXED_COSTS] + ['Fixed Cost', 'Office rent', 'OFC rent']
        return list(dict.fromkeys(categories))

    @classmethod
    def is_fixed_cost_category(cls, category_name):
        """
        Check if a category name is confidential / fixed cost (case-insensitive and keyword-aware).
        """
        if not category_name:
            return False
        cat_lower = str(category_name).strip().lower()
        fixed_cats_lower = [c.lower() for c in cls.get_fixed_cost_categories()]
        if cat_lower in fixed_cats_lower:
            return True
        for kw in cls.CONFIDENTIAL_KEYWORDS:
            if kw in cat_lower:
                return True
        return False

    @classmethod
    def get_fixed_cost_q(cls):
        """
        Returns a Q object matching any Fixed Cost / confidential expense by category, keywords, or is_confidential flag.
        """
        from django.db.models import Q
        categories = cls.get_fixed_cost_categories()
        q = Q(expense_type__in=categories) | Q(is_confidential=True)
        for kw in cls.CONFIDENTIAL_KEYWORDS:
            q |= Q(expense_type__icontains=kw)
        return q

    @property
    def is_fixed_cost(self):
        """Returns True if this expense is categorized as a Fixed Cost or confidential expense."""
        return bool(self.is_confidential) or self.is_fixed_cost_category(self.expense_type)

    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Clarification', 'Needs Clarification'),
        ('Clarification Provided', 'Clarification Provided'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    )
    
    title = models.CharField(max_length=255)
    employee_code = models.CharField(max_length=50, blank=True, null=True, help_text="Optional Employee Code for this expense")
    expense_type = models.CharField(max_length=100)
    is_confidential = models.BooleanField(default=False, db_index=True, help_text="Mark as confidential expense visible only to Admin, MD, Accounts, HR")
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    gst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    date = models.DateField()
    submitted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submitted_expenses')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='Pending')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_expenses')
    approved_at = models.DateTimeField(null=True, blank=True)
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    receipt = models.FileField(upload_to='expenses/receipts/', null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    payload = models.JSONField(blank=True, null=True, default=dict)

    def save(self, *args, **kwargs):
        if self.is_fixed_cost_category(self.expense_type):
            self.is_confidential = True
        super().save(*args, **kwargs)

    # Clarification workflow fields
    clarification_query = models.TextField(blank=True, null=True, help_text="Admin query on missing or incorrect information")
    clarification_response = models.TextField(blank=True, null=True, help_text="User's explanation or response")
    clarification_raised_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='clarifications_raised')
    clarification_raised_at = models.DateTimeField(null=True, blank=True)
    clarification_popup_seen = models.BooleanField(default=True, help_text="Set to False when admin raises clarification; True when user views/acknowledges")

    # Edit permission workflow fields
    EDIT_PERMISSION_CHOICES = (
        ('NONE', 'No Request'),
        ('PENDING', 'Pending Admin Approval'),
        ('APPROVED', 'Approved for Edit'),
        ('REJECTED', 'Rejected'),
    )
    edit_permission_status = models.CharField(
        max_length=20,
        choices=EDIT_PERMISSION_CHOICES,
        default='NONE',
        db_index=True,
        help_text="Status of admin approval for user to edit this expense"
    )
    edit_requested_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='expense_edit_requests'
    )
    edit_requested_at = models.DateTimeField(null=True, blank=True)
    edit_request_reason = models.TextField(blank=True, null=True, help_text="Reason user wants to edit this expense")
    edit_reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='expense_edits_reviewed'
    )
    edit_reviewed_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_clarification_unresolved(self):
        """Returns True if a clarification query was raised and the expense is not yet marked as approved (or rejected)."""
        return bool(self.clarification_query) and self.status not in ('Approved', 'Rejected')

    @property
    def expense_id(self):
        return f"e-{self.id:07d}" if self.id else ""

    @property
    def formatted_id(self):
        return f"e-{self.id:07d}" if self.id else ""

    @property
    def display_employee_code(self):
        if self.employee_code:
            code = self.employee_code.strip()
            if code.upper() in ['OFFICE', 'OFFICIAL', 'COMPANY']:
                return "OFFICE"
            return code
        if self.submitted_by and getattr(self.submitted_by, 'empid', None):
            return self.submitted_by.empid.strip()
        if self.submitted_by and getattr(self.submitted_by, 'username', None):
            return self.submitted_by.username.strip()
        return "N/A"

    @property
    def employee_user(self):
        if hasattr(self, '_cached_employee_user'):
            return self._cached_employee_user
        code = (self.employee_code or '').strip()
        if code.upper() in ['OFFICE', 'OFFICIAL', 'COMPANY']:
            return None
        if code:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            matched = User.objects.filter(models.Q(empid__iexact=code) | models.Q(username__iexact=code)).first()
            if matched:
                return matched
        return self.submitted_by

    @property
    def employee_name(self):
        if hasattr(self, '_cached_employee_name'):
            return self._cached_employee_name
        code = (self.employee_code or '').strip()
        if code.upper() in ['OFFICE', 'OFFICIAL', 'COMPANY']:
            return "Office / Company"
        user = self.employee_user
        if user:
            return user.get_full_name().strip() or user.first_name or user.username
        return ""

    def __str__(self):
        return f"{self.expense_id} - {self.title} - {self.amount} ({self.status})"

    @property
    def get_formatted_payload(self):
        if not self.payload:
            return {}
        formatted = {}
        for key, value in self.payload.items():
            if not value:
                continue
            formatted_key = key.replace('petrol_', '').replace('travel_', '').replace('courier_', '').replace('transport_', '').replace('_', ' ').title()
            if key == 'petrol_rate_per_km':
                formatted[formatted_key] = f"₹{value} / KM"
            elif key == 'petrol_total_distance':
                formatted[formatted_key] = f"{value} KM"
            elif key == 'petrol_calculated_cost':
                formatted[formatted_key] = f"₹{value}"
            elif isinstance(value, list):
                formatted[formatted_key] = ", ".join(str(v) for v in value if v)
            else:
                formatted[formatted_key] = value
        return formatted