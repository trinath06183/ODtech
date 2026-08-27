from decimal import Decimal
from django.db import models
from core.models import TimeStampedModel
from core.utils import money
from contacts.models import Contact
from inventory.models import Product
from django.utils import timezone

CURRENCY_CHOICES = [
    ('INR', 'INR (₹) - Indian Rupee'),
    ('USD', 'USD ($) - US Dollar'),
    ('EUR', 'EUR (€) - Euro'),
    ('GBP', 'GBP (£) - British Pound'),
    ('AED', 'AED (د.إ) - UAE Dirham'),
    ('SAR', 'SAR (ر.س) - Saudi Riyal'),
    ('CAD', 'CAD (CA$) - Canadian Dollar'),
    ('AUD', 'AUD (A$) - Australian Dollar'),
    ('SGD', 'SGD (S$) - Singapore Dollar'),
    ('JPY', 'JPY (¥) - Japanese Yen'),
]

CURRENCY_SYMBOLS = {
    'INR': '₹',
    'USD': '$',
    'EUR': '€',
    'GBP': '£',
    'AED': 'AED',
    'SAR': 'SAR',
    'CAD': 'CA$',
    'AUD': 'A$',
    'SGD': 'S$',
    'JPY': '¥',
}

CURRENCY_WORDS = {
    'INR': ('Rupees', 'Paise'),
    'USD': ('Dollars', 'Cents'),
    'EUR': ('Euros', 'Cents'),
    'GBP': ('Pounds', 'Pence'),
    'AED': ('Dirhams', 'Fils'),
    'SAR': ('Riyals', 'Halalas'),
    'CAD': ('Dollars', 'Cents'),
    'AUD': ('Dollars', 'Cents'),
    'SGD': ('Dollars', 'Cents'),
    'JPY': ('Yen', 'Sen'),
}

class Document(TimeStampedModel):
    CURRENCY_CHOICES = CURRENCY_CHOICES
    CURRENCY_SYMBOLS = CURRENCY_SYMBOLS
    CURRENCY_WORDS = CURRENCY_WORDS

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
    currency = models.CharField(max_length=10, default='INR', choices=CURRENCY_CHOICES, verbose_name="Currency")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    number = models.CharField(max_length=50, unique=True)
    date = models.DateField(default=timezone.now)
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE, related_name='documents')
    
    # Industrial & Transporter Fields (Optional)
    project_name = models.CharField(max_length=255, blank=True, null=True)
    site_address = models.TextField(blank=True, null=True)
    eway_bill = models.CharField(max_length=100, blank=True, null=True, verbose_name="E-Way Bill No.")
    eway_bill_date = models.DateField(blank=True, null=True, verbose_name="E-Way Bill Date")
    po_reference_number = models.CharField(max_length=100, blank=True, null=True, verbose_name="PO Reference Number")
    po_date = models.DateField(blank=True, null=True, verbose_name="PO Reference Date")
    place_of_supply = models.CharField(max_length=100, default='21-Odisha', blank=True, null=True, verbose_name="Place of Supply")
    source_document = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='converted_documents')
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_documents',
        verbose_name='Created By',
    )
    
    # Transporter Details (For Delivery Challan)
    transporter_details = models.CharField(max_length=255, blank=True, null=True, default='Local Transportation', verbose_name="Transporter Details")
    vehicle_number = models.CharField(max_length=100, blank=True, null=True, verbose_name="Transporter Vehicle No.")
    transport_doc_no = models.CharField(max_length=100, blank=True, null=True, verbose_name="Transporter Doc No.")
    transport_doc_date = models.DateField(blank=True, null=True, verbose_name="Transporter Doc Date")
    transport_reason = models.TextField(blank=True, null=True, default='Refilling only, No Commercial involvement.', verbose_name="Transport Reason")
    
    # Totals
    subtotal = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    tax_total = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    grand_total = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    terms_and_conditions = models.TextField(blank=True, null=True)
    show_gst = models.BooleanField(default=False)
    split_gst = models.BooleanField(default=False)
    force_igst = models.BooleanField(default=False)
    show_payment_summary = models.BooleanField(default=True)
    payment_milestones = models.TextField(blank=True, null=True)
    numbering_mode = models.CharField(max_length=10, default='auto')
    table_columns = models.JSONField(blank=True, null=True)
    enable_warranty = models.BooleanField(default=False)
    shipping_address = models.TextField(blank=True, null=True)
    shipping_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Shipping Name")
    repeat_header = models.BooleanField(default=False)
    
    # Seller / Dispatch Location Details (Bill From & Ship From)
    bill_from_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Bill From Name")
    bill_from_address = models.TextField(blank=True, null=True, verbose_name="Bill From Address")
    bill_from_gstin = models.CharField(max_length=15, blank=True, null=True, verbose_name="Bill From GSTIN")
    ship_from_name = models.CharField(max_length=255, blank=True, null=True, verbose_name="Ship From Name / Dispatch Location")
    ship_from_address = models.TextField(blank=True, null=True, verbose_name="Ship From Address / Warehouse")
    ship_from_gstin = models.CharField(max_length=15, blank=True, null=True, verbose_name="Ship From GSTIN")
    
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

    def get_access_token(self):
        """Generate a cryptographically signed unguessable access token for public sharing without login."""
        from django.core.signing import Signer
        signer = Signer(salt="document-public-view-salt")
        return signer.sign(str(self.id))

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
        # Respect company-wide "Show T&C" setting
        try:
            from config.models import CompanyProfile
            company = CompanyProfile.objects.first()
            if company and not company.show_terms:
                return []
        except Exception:
            pass

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

    @property
    def currency_symbol(self):
        return CURRENCY_SYMBOLS.get(self.currency, '₹')

    def to_words(self, amount):
        main_unit, sub_unit = CURRENCY_WORDS.get(self.currency, ('Rupees', 'Paise'))
        try:
            from num2words import num2words
            import math
            main_amt = math.floor(amount)
            sub_amt = round((amount - main_amt) * 100)
            
            lang = 'en_IN' if self.currency == 'INR' else 'en'
            main_words = num2words(main_amt, lang=lang).replace(',', '').title()
            if sub_amt > 0:
                sub_words = num2words(sub_amt, lang=lang).replace(',', '').title()
                return f"{main_words} {main_unit} and {sub_words} {sub_unit} Only"
            else:
                return f"{main_words} {main_unit} Only"
        except Exception:
            return f"{amount} {main_unit} Only"

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

    def get_all_linked_document_numbers(self):
        """
        Recursively traverses all linked documents (via DocumentLink and source_document)
        to return all connected document numbers in the document lifecycle.
        """
        from django.contrib.contenttypes.models import ContentType
        from django.db.models import Q
        from core.models import DocumentLink

        visited_ids = {self.id}
        queue = [self.id]

        doc_ct = ContentType.objects.get_for_model(self.__class__)

        while queue:
            curr_id = queue.pop(0)

            # 1. DocumentLink links
            links = DocumentLink.objects.filter(
                Q(source_type=doc_ct, source_id=str(curr_id)) |
                Q(target_type=doc_ct, target_id=str(curr_id))
            ).values_list('source_type_id', 'source_id', 'target_type_id', 'target_id')

            for s_ct_id, s_id, t_ct_id, t_id in links:
                if s_ct_id == doc_ct.id:
                    try:
                        s_int = int(s_id)
                        if s_int not in visited_ids:
                            visited_ids.add(s_int)
                            queue.append(s_int)
                    except (ValueError, TypeError):
                        pass
                if t_ct_id == doc_ct.id:
                    try:
                        t_int = int(t_id)
                        if t_int not in visited_ids:
                            visited_ids.add(t_int)
                            queue.append(t_int)
                    except (ValueError, TypeError):
                        pass

            # 2. source_document relationships
            related_docs = Document.objects.filter(
                Q(id=curr_id) | Q(source_document_id=curr_id)
            ).values_list('id', 'source_document_id')

            for d_id, src_id in related_docs:
                if d_id and d_id not in visited_ids:
                    visited_ids.add(d_id)
                    queue.append(d_id)
                if src_id and src_id not in visited_ids:
                    visited_ids.add(src_id)
                    queue.append(src_id)

        return list(Document.objects.filter(id__in=visited_ids).values_list('number', flat=True))

    @property
    def amount_paid(self):
        from django.db.models import Sum
        from payments.models import Payment
        doc_numbers = self.get_all_linked_document_numbers()
        return Payment.objects.filter(document_ref__in=doc_numbers).aggregate(t=Sum('amount'))['t'] or 0

    @property
    def payments_list(self):
        from payments.models import Payment
        doc_numbers = self.get_all_linked_document_numbers()
        return Payment.objects.filter(document_ref__in=doc_numbers).order_by('-date')

    @property
    def balance_due(self):
        return self.grand_total - self.amount_paid

    @property
    def lifecycle_payment_status(self):
        """
        Calculates payment status by checking if this document is an invoice
        and checking any child/linked documents that are invoices.
        """
        if self.type == 'INV':
            if self.balance_due <= 0 and self.grand_total > 0:
                return 'Paid'
            elif self.amount_paid > 0:
                return 'Partially Paid'
            return 'Unpaid'
            
        doc_numbers = self.get_all_linked_document_numbers()
        linked_invoices = Document.objects.filter(number__in=doc_numbers, type='INV')
        
        if linked_invoices.exists():
            total_invoiced = sum(inv.grand_total for inv in linked_invoices)
            total_paid = sum(inv.amount_paid for inv in linked_invoices)
            if total_invoiced > 0:
                if total_paid >= total_invoiced:
                    return 'Paid'
                elif total_paid > 0:
                    return 'Partially Paid'
                return 'Unpaid'
        
        if self.amount_paid > 0:
            if self.balance_due <= 0 and self.grand_total > 0:
                return 'Paid'
            return 'Partially Paid'
            
        return 'N/A'

    def get_linked_documents(self):
        from django.contrib.contenttypes.models import ContentType
        from django.db.models import Q
        from core.models import DocumentLink
        
        doc_ct = ContentType.objects.get_for_model(self.__class__)
        return DocumentLink.objects.filter(
            Q(source_type=doc_ct, source_id=str(self.id)) | 
            Q(target_type=doc_ct, target_id=str(self.id))
        ).order_by('-created_at')

    class Meta:
        ordering = ['-date', '-id']
        indexes = [
            models.Index(fields=['number']),
            models.Index(fields=['type', 'date']),
            models.Index(fields=['contact', 'date']),
            models.Index(fields=['status']),
        ]

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
