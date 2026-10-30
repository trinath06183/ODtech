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



class ExecutionPlanItem(models.Model):
    PLAN_TYPE_CHOICES = (
        ('booking', 'Order Booking Plan'),
        ('sales', 'Sales Plan'),
    )
    plan_type = models.CharField(max_length=20, choices=PLAN_TYPE_CHOICES, default='booking', db_index=True)
    month = models.DateField(help_text="First day of planned month", db_index=True)
    customer_name = models.CharField(max_length=255)
    item_description = models.TextField(blank=True, default='', verbose_name="Item Description / Project Name")
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1.00)
    uom = models.CharField(max_length=50, default='Nos', verbose_name="Unit of Measure")
    probable_order_value = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, verbose_name="Probable Order Value")
    total_order_value = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, verbose_name="Total Order Value")
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=18.00, verbose_name="GST %")
    including_gst_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, verbose_name="Including GST Amount")
    order_status = models.CharField(max_length=255, default='Pending')
    is_supplied = models.BooleanField(default=False, help_text="Triggers green highlight if supplied/completed")
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name = 'Execution Plan Item'
        verbose_name_plural = 'Execution Plan Items'

    def save(self, *args, **kwargs):
        qty = self.quantity if self.quantity is not None else 1
        rate = self.probable_order_value if self.probable_order_value is not None else 0
        if not self.total_order_value or self.total_order_value == 0:
            self.total_order_value = round(qty * rate, 2)
        gst = self.gst_rate if self.gst_rate is not None else 18
        if not self.including_gst_amount or self.including_gst_amount == 0:
            self.including_gst_amount = round(self.total_order_value * (1 + (gst / 100)), 2)
        status_lower = (self.order_status or '').lower()
        if 'supplied' in status_lower or 'completed' in status_lower or 'delivered' in status_lower:
            self.is_supplied = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"[{self.get_plan_type_display()}] {self.customer_name} - {self.item_description[:30]}"
