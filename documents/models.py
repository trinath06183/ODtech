from decimal import Decimal
from django.db import models
from core.models import TimeStampedModel
from core.utils import money
from contacts.models import Contact
from inventory.models import Product
from django.utils import timezone

class Document(TimeStampedModel):
    DOCUMENT_TYPES = (
        ('QTN', 'Quotation'),
        ('INV', 'Invoice'),
        ('PRO', 'Proforma Invoice'),
        ('CHL', 'Delivery Challan'),
        ('PO', 'Purchase Order'),
        ('CRN', 'Credit Note'),
        ('DBN', 'Debit Note'),
    )
    STATUS_CHOICES = (
        ('Draft', 'Draft'),
        ('Approved', 'Approved'),
        ('Cancelled', 'Cancelled'),
    )
    
    type = models.CharField(max_length=10, choices=DOCUMENT_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    number = models.CharField(max_length=50, unique=True)
    date = models.DateField(default=timezone.now)
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='documents')
    
    # Industrial Fields (Optional)
    project_name = models.CharField(max_length=255, blank=True, null=True)
    site_address = models.TextField(blank=True, null=True)
    eway_bill = models.CharField(max_length=50, blank=True, null=True)
    po_reference_number = models.CharField(max_length=100, blank=True, null=True, verbose_name="PO Reference Number")
    po_date = models.DateField(blank=True, null=True, verbose_name="PO Reference Date")
    place_of_supply = models.CharField(max_length=100, default='21-Odisha', blank=True, null=True, verbose_name="Place of Supply")
    source_document = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='converted_documents')
    
    # Totals
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    tax_total = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    grand_total = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    terms_and_conditions = models.TextField(blank=True, null=True)
    show_gst = models.BooleanField(default=False)
    split_gst = models.BooleanField(default=False)
    force_igst = models.BooleanField(default=False)
    payment_milestones = models.TextField(blank=True, null=True)
    numbering_mode = models.CharField(max_length=10, default='auto')
    table_columns = models.JSONField(blank=True, null=True)
    enable_warranty = models.BooleanField(default=False)
    shipping_address = models.TextField(blank=True, null=True)
    repeat_header = models.BooleanField(default=False)
    
    DISCOUNT_TYPES = (
        ('none', 'No Discount'),
        ('fixed', 'Global Fixed'),
        ('percentage', 'Global Percentage'),
        ('individual', 'Individual (₹)'),
        ('individual_pct', 'Individual (%)'),
    )
    discount_type = models.CharField(max_length=15, choices=DISCOUNT_TYPES, default='none')
    discount_value = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))

    @property
    def gross_subtotal(self):
        return sum(item.quantity * item.unit_price for item in self.items.all())

    @property
    def total_discount(self):
        return sum(item.discount for item in self.items.all())

    @classmethod
    def get_default_terms(cls, document_type):
        DEFAULT_TERMS_QTN = (
            "Payment: 40% advance with PO against PI, 30% After machine delivery and work start at site, 20% after machine Installation and commissioning & 10% after project handover.\n"
            "Delivery: Within 06 to 08 Weeks from date of PO & Payment confirmation\n"
            "Taxes: GST 18% As applicable on above price\n"
            "Freight or Courier : Free Door Delivery\n"
            "Quotation Validity: 15 days\n"
            "Warranty: 03 Year warranty on Products(Warranty excludes on wear parts like Torch and it's Hoses, Electrodes, Safety items and consumables)"
        )
        DEFAULT_TERMS_OTHER = (
            "Payment: 40% advance with PO against PI, 30% After machine delivery and work start at site, 20% after machine Installation and commissioning & 10% after project handover.\n"
            "Delivery: Within 06 to 08 Weeks from date of PO & Payment confirmation\n"
            "Taxes: GST 18% As applicable on above price\n"
            "Freight or Courier : Free Door Delivery\n"
            "Warranty: 03 Year warranty on Products(Warranty excludes on wear parts like Torch and it's Hoses, Electrodes, Safety items and consumables)"
        )
        if document_type == 'QTN':
            return DEFAULT_TERMS_QTN
        return DEFAULT_TERMS_OTHER

    @property
    def terms_list(self):
        terms = self.terms_and_conditions
        if terms is None:
            terms = self.get_default_terms(self.type)
        return [line.strip() for line in terms.split('\n') if line.strip()]

    @property
    def is_igst(self):
        if self.force_igst:
            return True
        from .services import TaxService
        return TaxService.is_igst(self.contact)

    @property
    def cgst_amount(self):
        return self.tax_total / 2

    @property
    def sgst_amount(self):
        return self.tax_total / 2

    def to_words(self, amount):
        try:
            from num2words import num2words
            import math
            rupees = math.floor(amount)
            paise = round((amount - rupees) * 100)
            
            rupees_words = num2words(rupees, lang='en_IN').replace(',', '').title()
            if paise > 0:
                paise_words = num2words(paise, lang='en_IN').replace(',', '').title()
                return f"{rupees_words} Rupees and {paise_words} Paise Only"
            else:
                return f"{rupees_words} Rupees Only"
        except ImportError:
            return f"{amount} Rupees Only"

    @property
    def amount_in_words(self):
        return self.to_words(self.grand_total)

    @property
    def subtotal_in_words(self):
        return self.to_words(self.subtotal)

    @property
    def payment_milestones_list(self):
        if not self.payment_milestones:
            return []
        import json
        try:
            return json.loads(self.payment_milestones)
        except Exception:
            return []

    @property
    def amount_paid(self):
        from django.db.models import Sum
        from payments.models import Payment
        return Payment.objects.filter(document_ref=self.number).aggregate(t=Sum('amount'))['t'] or 0
        
    @property
    def payments_list(self):
        from payments.models import Payment
        return Payment.objects.filter(document_ref=self.number).order_by('-date')

    @property
    def balance_due(self):
        return self.grand_total - self.amount_paid

    def __str__(self):
        return f"{self.type} - {self.number} ({self.status})"


class DocumentItem(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    part_number = models.CharField(max_length=100, blank=True, null=True)
    serial_number = models.TextField(blank=True, null=True, verbose_name="Serial Number")
    has_warranty = models.BooleanField(default=False)
    model = models.CharField(max_length=100, blank=True, null=True)
    warranty_period = models.CharField(max_length=50, blank=True, null=True)
    warranty_start_date = models.DateField(blank=True, null=True)
    unit = models.CharField(max_length=20, blank=True, null=True)
    hsn_code = models.CharField(max_length=50, blank=True, null=True)
    quantity = models.DecimalField(max_digits=15, decimal_places=2)
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)
    discount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('18.00'))
    tax_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    total = models.DecimalField(max_digits=15, decimal_places=2)

    def save(self, *args, **kwargs):
        base = (self.quantity * self.unit_price) - self.discount
        self.tax_amount = money(base * (self.tax_rate / 100))
        self.total = money(base + self.tax_amount)
        super().save(*args, **kwargs)

    @property
    def base_amount(self):
        return (self.quantity * self.unit_price) - self.discount

    def __str__(self):
        return f"{self.product.name} - {self.document.number}"
