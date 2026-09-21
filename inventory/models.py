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
    reference_document = models.CharField(max_length=100, blank=True, null=True,
                                           help_text='Reference document number (e.g. PO-001)')
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


# --- Bill of Materials (BOM) & Assembly Work Orders ----------------------------
class BillOfMaterials(TimeStampedModel):
    finished_product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='boms',
        help_text="Finished product manufactured or assembled"
    )
    bom_number = models.CharField(max_length=50, unique=True, help_text="e.g. BOM-2026-001")
    name = models.CharField(max_length=255, help_text="e.g. Standard MIG-250 Assembly Specification")
    version = models.CharField(max_length=20, default="1.0")
    is_active = models.BooleanField(default=True)
    labor_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Direct labor cost per unit")
    overhead_cost = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, help_text="Overhead cost per unit")
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Bill of Materials"
        verbose_name_plural = "Bills of Materials"

    @property
    def total_component_cost(self):
        from decimal import Decimal
        total = Decimal('0.00')
        for item in self.items.select_related('component_product').all():
            total += item.line_cost
        return total

    @property
    def unit_production_cost(self):
        from decimal import Decimal
        return self.total_component_cost + (self.labor_cost or Decimal('0.00')) + (self.overhead_cost or Decimal('0.00'))

    def __str__(self):
        return f"{self.bom_number}: {self.finished_product.name} (v{self.version})"


class BOMItem(TimeStampedModel):
    bom = models.ForeignKey(BillOfMaterials, on_delete=models.CASCADE, related_name='items')
    component_product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name='bom_usages',
        help_text="Raw material or sub-component item"
    )
    quantity_required = models.DecimalField(max_digits=15, decimal_places=4, help_text="Quantity required per 1 finished unit")
    unit = models.CharField(max_length=50, default='Nos')
    scrap_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Expected scrap/wastage %")
    notes = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['id']

    @property
    def effective_quantity(self):
        from decimal import Decimal
        scrap = (self.scrap_percentage or Decimal('0.00')) / Decimal('100.00')
        return self.quantity_required * (Decimal('1.00') + scrap)

    @property
    def line_cost(self):
        from decimal import Decimal
        price = self.component_product.purchase_price or Decimal('0.00')
        return self.effective_quantity * price

    def __str__(self):
        return f"{self.component_product.name} x {self.quantity_required} {self.unit}"


class AssemblyWorkOrder(TimeStampedModel):
    STATUS_CHOICES = [
        ('Draft', 'Draft'),
        ('Scheduled', 'Scheduled'),
        ('In Production', 'In Production'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    ]

    order_number = models.CharField(max_length=50, unique=True, help_text="e.g. WO-2026-0001")
    bom = models.ForeignKey(BillOfMaterials, on_delete=models.PROTECT, related_name='work_orders')
    finished_product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='work_orders')
    quantity_to_produce = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    assigned_technician = models.CharField(max_length=150, blank=True, null=True, help_text="Technician or supervisor name")
    start_date = models.DateField(blank=True, null=True)
    target_date = models.DateField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    serial_numbers_produced = models.TextField(blank=True, null=True, help_text="Comma or newline-separated serial numbers of completed units")
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assembly_work_orders'
    )

    class Meta:
        ordering = ['-created_at']

    @property
    def total_cost(self):
        from decimal import Decimal
        return self.bom.unit_production_cost * Decimal(self.quantity_to_produce)

    def __str__(self):
        return f"{self.order_number} ({self.finished_product.name} x {self.quantity_to_produce}) - {self.status}"