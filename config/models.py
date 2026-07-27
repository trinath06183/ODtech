from django.db import models
from core.models import TimeStampedModel

class CompanyProfile(TimeStampedModel):
    name = models.CharField(max_length=255, default="ODtech Solutions")
    gstin = models.CharField(max_length=15, blank=True, null=True)
    pan = models.CharField(max_length=10, blank=True, null=True)
    logo = models.ImageField(upload_to='company/', blank=True, null=True)
    signature = models.ImageField(upload_to='company/', blank=True, null=True)
    terms_conditions = models.TextField(blank=True, null=True)
    
    # Prefixes
    invoice_prefix = models.CharField(max_length=10, default="INV-")
    quotation_prefix = models.CharField(max_length=10, default="QTN-")
    po_prefix = models.CharField(max_length=10, default="PO-")
    challan_prefix = models.CharField(max_length=10, default="CHL-")

    # Sequence tracking
    seq_qtn = models.IntegerField(default=0, verbose_name="Last Quotation Sequence")
    seq_inv = models.IntegerField(default=0, verbose_name="Last Invoice Sequence")
    seq_pro = models.IntegerField(default=0, verbose_name="Last Proforma Invoice Sequence")
    seq_chl = models.IntegerField(default=0, verbose_name="Last Delivery Challan Sequence")
    seq_po = models.IntegerField(default=0, verbose_name="Last Purchase Order Sequence")
    seq_crn = models.IntegerField(default=0, verbose_name="Last Credit Note Sequence")
    seq_dbn = models.IntegerField(default=0, verbose_name="Last Debit Note Sequence")

    # Document number format
    DOC_NUMBER_FORMAT_CHOICES = [
        ('OD-{FY}-{MM}-{N}',            'OD-26-07-285  (FY + Month + S.No.)'),
        ('OD-{TYPE}-{FY}-{MM}-{N}',     'OD-INV-26-07-285  (Type + FY + Month + S.No.)'),
        ('OD-{TYPE}-{FYFY}-{MM}-{N}',   'OD-INV-2627-07-285  (Type + Full FY + Month + S.No.)'),
    ]
    doc_number_format = models.CharField(
        max_length=40,
        choices=DOC_NUMBER_FORMAT_CHOICES,
        default='OD-{FY}-{MM}-{N}',
    )
    
    # Security/Action Settings
    allow_document_deletion = models.BooleanField(
        default=False,
        verbose_name="Allow Document Deletion",
        help_text="If disabled, the delete option for documents will be hidden and blocked."
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Ensure only one record exists
        if self.__class__.objects.count():
            self.pk = self.__class__.objects.first().pk
        super().save(*args, **kwargs)

from django.conf import settings

class DocumentFolder(TimeStampedModel):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='subfolders')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

class CompanyDocument(TimeStampedModel):
    folder = models.ForeignKey(DocumentFolder, on_delete=models.CASCADE, related_name='documents', null=True)
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='company/documents/')
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='uploaded_company_docs')
    
    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
