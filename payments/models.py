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

class Expense(TimeStampedModel):
    EXPENSE_TYPES = (
        ('Daily Expenses', (
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
        )),
        ('Fixed Cost', (
            ('Staff salary', 'Staff salary'),
            ('OFC rent', 'OFC rent'),
            ('Electricity bill', 'Electricity bill'),
            ('Internet Bill', 'Internet Bill'),
            ('Google workspace', 'Google workspace'),
            ('Website and hosting cost', 'Website and hosting cost'),
            ('Other Fixed', 'Other'),
        ))
    )
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    )
    
    title = models.CharField(max_length=255)
    employee_code = models.CharField(max_length=50, blank=True, null=True, help_text="Optional Employee Code for this expense")
    expense_type = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    gst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    date = models.DateField()
    submitted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submitted_expenses')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_expenses')
    approved_at = models.DateTimeField(null=True, blank=True)
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    receipt = models.FileField(upload_to='expenses/receipts/', null=True, blank=True)
    notes = models.TextField(blank=True, null=True)
    payload = models.JSONField(blank=True, null=True, default=dict)

    def __str__(self):
        return f"{self.title} - {self.amount} ({self.status})"

    @property
    def get_formatted_payload(self):
        if not self.payload:
            return {}
        formatted = {}
        for key, value in self.payload.items():
            formatted_key = key.replace('_', ' ').title()
            if isinstance(value, list):
                formatted[formatted_key] = ", ".join(str(v) for v in value)
            else:
                formatted[formatted_key] = value
        return formatted