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
    document = models.ForeignKey('documents.Document', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments', help_text="Specific invoice this payment adjusts")
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    payment_mode = models.CharField(max_length=20, choices=PAYMENT_MODES)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    date = models.DateField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.contact.name} - {self.amount} ({self.date})"
