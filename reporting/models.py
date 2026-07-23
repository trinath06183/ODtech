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
