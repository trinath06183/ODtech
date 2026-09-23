from django.db import models



class PlannedOrder(models.Model):
    title = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    payments_received = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    expected_month = models.DateField(help_text="Set to the first day of the month it is planned for")
    status = models.CharField(max_length=255, default='Pending')
    completed_month = models.DateField(null=True, blank=True, help_text="The month it was actually completed")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class PlannedPurchase(models.Model):
    title = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    payments_given = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    expected_month = models.DateField(help_text="Set to the first day of the month it is planned for")
    status = models.CharField(max_length=255, default='Pending')
    completed_month = models.DateField(null=True, blank=True, help_text="The month it was actually completed")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


from django.conf import settings

class PaymentReminder(models.Model):
    REMINDER_TYPE_CHOICES = (
        ('receivable', 'Receivable'),
        ('payable', 'Payable'),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_reminders'
    )
    document = models.ForeignKey(
        'documents.Document',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='payment_reminders'
    )
    title = models.CharField(max_length=255)
    party = models.CharField(max_length=255, blank=True, default='')
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    due_date = models.DateField(null=True, blank=True)
    reminder_type = models.CharField(max_length=20, default='receivable', choices=REMINDER_TYPE_CHOICES)
    is_urgent = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_date', '-created_at']

    def __str__(self):
        return f"{self.title} - {self.party} (₹{self.amount})"

