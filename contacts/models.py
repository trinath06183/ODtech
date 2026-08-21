from django.db import models
from core.models import TimeStampedModel
from core.validators import normalize_tax_identifier, validate_gstin, validate_pan

class Contact(TimeStampedModel):
    CONTACT_TYPES = (
        ('Customer', 'Customer'),
        ('Vendor', 'Vendor'),
        ('Both', 'Both'),
    )
    name = models.CharField(max_length=255)
    contact_type = models.CharField(max_length=20, choices=CONTACT_TYPES)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    
    # Government & Registry specific
    gem_id = models.CharField(max_length=50, blank=True, null=True)
    department_registry_number = models.CharField(max_length=100, blank=True, null=True)
    gstin = models.CharField(max_length=15, blank=True, null=True, validators=[validate_gstin])
    pan = models.CharField(max_length=10, blank=True, null=True, validators=[validate_pan])

    def save(self, *args, **kwargs):
        self.gstin = normalize_tax_identifier(self.gstin) or None
        self.pan = normalize_tax_identifier(self.pan) or None
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['gstin']),
            models.Index(fields=['phone']),
            models.Index(fields=['contact_type']),
        ]

    def __str__(self):
        return f"{self.name} ({self.contact_type})"

class Address(TimeStampedModel):
    ADDRESS_TYPES = (
        ('Billing', 'Billing'),
        ('Shipping', 'Shipping'),
    )
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='addresses')
    address_type = models.CharField(max_length=20, choices=ADDRESS_TYPES)
    address = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name_plural = "Addresses"

    def __str__(self):
        return f"{self.contact.name} - {self.address_type}"

class ContactPerson(TimeStampedModel):
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='contact_persons')
    name = models.CharField(max_length=255)
    designation = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return f"{self.name} - {self.contact.name}"


class VendorQuote(TimeStampedModel):
    vendor = models.ForeignKey(
        Contact, 
        on_delete=models.CASCADE, 
        related_name='vendor_quotes',
        limit_choices_to={'contact_type__in': ['Vendor', 'Both']}
    )
    product = models.ForeignKey(
        'inventory.Product', 
        on_delete=models.CASCADE, 
        related_name='vendor_quotes'
    )
    quoted_price = models.DecimalField(max_digits=15, decimal_places=2)
    quote_date = models.DateField()
    valid_until = models.DateField(blank=True, null=True)
    lead_time_days = models.IntegerField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['quoted_price']

    def __str__(self):
        return f"{self.vendor.name} - {self.product.name} ({self.quoted_price})"

