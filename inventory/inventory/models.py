from django.db import models
from core.models import TimeStampedModel

class Product(TimeStampedModel):
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, unique=True)
    hsn_code = models.CharField(max_length=50, blank=True, null=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=18.00)
    selling_price = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    purchase_price = models.DecimalField(max_digits=15, decimal_places=2, default=0.00,
                                         help_text="Cost price / purchase price of the item")
    unit = models.CharField(max_length=50, default='Nos')
    brand = models.CharField(max_length=100, blank=True, null=True)
    category = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    warranty_months = models.IntegerField(default=12, help_text="Default warranty period in months")
    reorder_level = models.DecimalField(max_digits=15, decimal_places=2, default=0,
                                        help_text="Trigger low-stock alert when stock falls below this")

    @property
    def current_stock(self):
        from inventory.services import StockService
        return StockService.get_available_stock(self.id)

    @property
    def is_low_stock(self):
        return self.reorder_level > 0 and self.current_stock < self.reorder_level

    def __str__(self):
        return f"{self.name} ({self.sku})"

class ProductDescription(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='additional_descriptions')
    title = models.CharField(max_length=255, blank=True, null=True)
    content = models.TextField()

    def __str__(self):
        return f"{self.product.name} - {self.title or 'Description'}"

class StockTransaction(TimeStampedModel):
    TRANSACTION_TYPES = (
        ('IN', 'IN'),
        ('OUT', 'OUT'),
        ('ADJUSTMENT', 'ADJUSTMENT'),
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_transactions')
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    quantity = models.DecimalField(max_digits=15, decimal_places=2) # positive for IN, negative for OUT
    reference_document = models.ForeignKey('documents.Document', on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_transactions')
    batch_number = models.CharField(max_length=100, blank=True, null=True)
    serial_number = models.CharField(max_length=100, blank=True, null=True)
    reason = models.CharField(max_length=255, blank=True, null=True,
                              help_text="Reason for manual adjustment (e.g., damaged, expired)")
    remarks = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.product.name} - {self.transaction_type} ({self.quantity})"


# --- Warranty Registration -----------------------------------------------------
class WarrantyRegistration(TimeStampedModel):
    invoice_number   = models.CharField(max_length=100)
    serial_number    = models.TextField()
    invoice_date     = models.DateField()
    invoice_amount   = models.DecimalField(max_digits=15, decimal_places=2,
                                           help_text="Total invoice amount including GST")
    company_name     = models.CharField(max_length=255)
    gst_number       = models.CharField(max_length=20, blank=True, null=True)
    email            = models.EmailField()
    contact_number   = models.CharField(max_length=20)
    product_image    = models.ImageField(upload_to='warranty/product_images/')
    invoice_document = models.FileField(upload_to='warranty/invoices/',
                                        help_text="PDF or image of the invoice")

    def __str__(self):
        return f"Reg: {self.invoice_number} / S/N {self.serial_number}"


# --- Warranty Claim ------------------------------------------------------------
import uuid

def _generate_claim_number():
    from django.utils import timezone
    year = timezone.now().year
    uid  = uuid.uuid4().hex[:6].upper()
    return f"WC-{year}-{uid}"


class WarrantyClaim(TimeStampedModel):
    STATUS_CHOICES = [
        ('Pending',   'Pending'),
        ('In Review', 'In Review'),
        ('Resolved',  'Resolved'),
        ('Rejected',  'Rejected'),
    ]

    registration        = models.ForeignKey(WarrantyRegistration, on_delete=models.CASCADE,
                                            related_name='claims')
    claim_number        = models.CharField(max_length=30, unique=True, editable=False)
    problem_description = models.TextField()
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    status_reason       = models.TextField(blank=True, null=True, help_text="Reason for the current status")
    attachment_1        = models.FileField(upload_to='warranty/claim_attachments/', blank=True, null=True)
    attachment_2        = models.FileField(upload_to='warranty/claim_attachments/', blank=True, null=True)
    attachment_3        = models.FileField(upload_to='warranty/claim_attachments/', blank=True, null=True)
    product_photo_1     = models.ImageField(upload_to='warranty/claim_photos/', blank=True, null=True)
    product_photo_2     = models.ImageField(upload_to='warranty/claim_photos/', blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.claim_number:
            num = _generate_claim_number()
            while WarrantyClaim.objects.filter(claim_number=num).exists():
                num = _generate_claim_number()
            self.claim_number = num
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Claim {self.claim_number} [{self.status}]"