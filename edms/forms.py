"""
EDMS Forms
==========
All Django forms for the Enterprise Document Management System.
"""

from django import forms
from django.conf import settings
from django.utils.text import slugify
from edms.models import (
    EDMSDocument, EDMSDocumentCategory, EDMSDocumentTag,
    EDMSDocumentVersion, EDMSVendor, EDMSCompanyProfile,
    Department, EDMSDocumentAccess, EDMSSavedSearch,
)
from contacts.models import Contact


# ── Shared Widgets ────────────────────────────────────────────────────────────

TAILWIND_INPUT  = 'w-full px-4 py-2.5 rounded-xl border border-gray-200 bg-white/70 focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent text-sm'
TAILWIND_SELECT = 'w-full px-4 py-2.5 rounded-xl border border-gray-200 bg-white/70 focus:outline-none focus:ring-2 focus:ring-blue-400 text-sm'
TAILWIND_AREA   = 'w-full px-4 py-2.5 rounded-xl border border-gray-200 bg-white/70 focus:outline-none focus:ring-2 focus:ring-blue-400 text-sm h-24 resize-none'


# ─── Document Upload Form (Step 1 — File Selection) ──────────────────────────

class DocumentFileForm(forms.Form):
    """Step 1 of the upload wizard: just the file."""
    file = forms.FileField(
        label='Select Document',
        help_text=(
            f"Allowed types: PDF, Word, Excel, Images, etc. "
            f"Max size: {getattr(settings, 'EDMS_MAX_UPLOAD_MB', 50)} MB"
        ),
        widget=forms.ClearableFileInput(attrs={
            'class': 'hidden',
            'id':    'edms-file-input',
            'accept': ','.join(getattr(settings, 'EDMS_ALLOWED_EXTENSIONS', [])),
        }),
    )

    def clean_file(self):
        from edms.services.upload_service import UploadService
        f = self.cleaned_data['file']
        UploadService.validate(f)
        return f


# ─── Document Metadata Form (Step 2 — Metadata) ──────────────────────────────

class DocumentMetadataForm(forms.ModelForm):
    """
    Step 2 of the upload wizard: metadata fields.
    Can also be used standalone for editing existing documents.
    """
    tags = forms.ModelMultipleChoiceField(
        queryset=EDMSDocumentTag.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple(),
        label='Tags',
    )
    new_tags = forms.CharField(
        required=False,
        label='Add New Tags',
        help_text='Comma-separated new tags to create and attach',
        widget=forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'finance, 2025, certified'}),
    )
    issue_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}, format='%Y-%m-%d'),
        input_formats=['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d'],
    )
    expiry_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}, format='%Y-%m-%d'),
        input_formats=['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d'],
    )
    invoice_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}, format='%Y-%m-%d'),
        input_formats=['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d'],
    )

    class Meta:
        model  = EDMSDocument
        fields = [
            'title', 'description', 'category', 'department',
            'document_type', 'keywords', 'reference_number',
            'issue_date', 'expiry_date', 'access_level',
            'is_confidential', 'approval_status',
            'company', 'contact_vendor', 'party_name',
            'po_number', 'invoice_number', 'invoice_date',
            'bill_number', 'amount', 'tax_amount', 'currency',
            'payment_status', 'tags',
        ]
        widgets = {
            'title':            forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description':      forms.Textarea(attrs={'class': TAILWIND_AREA}),
            'category':         forms.Select(attrs={'class': TAILWIND_SELECT}),
            'department':       forms.Select(attrs={'class': TAILWIND_SELECT}),
            'document_type':    forms.Select(attrs={'class': TAILWIND_SELECT}),
            'keywords':         forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'gst, 2024, annual'}),
            'reference_number': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'issue_date':       forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}, format='%Y-%m-%d'),
            'expiry_date':      forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}, format='%Y-%m-%d'),
            'access_level':     forms.Select(attrs={'class': TAILWIND_SELECT}),
            'is_confidential':  forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded text-blue-600'}),
            'approval_status':  forms.Select(attrs={'class': TAILWIND_SELECT}),
            'company':          forms.Select(attrs={'class': TAILWIND_SELECT}),
            'contact_vendor':   forms.Select(attrs={'class': TAILWIND_SELECT, 'id': 'id_contact_vendor'}),
            'party_name':       forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'e.g. Tata Steel Ltd, HDFC Bank...'}),
            'po_number':        forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'invoice_number':   forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'invoice_date':     forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}, format='%Y-%m-%d'),
            'bill_number':      forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'amount':           forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}),
            'tax_amount':       forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}),
            'currency':         forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'payment_status':   forms.Select(attrs={'class': TAILWIND_SELECT}),
            'tags':             forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'approval_status' in self.fields:
            self.fields['approval_status'].required = False
        if 'currency' in self.fields:
            self.fields['currency'].required = False
            if not self.initial.get('currency'):
                self.initial['currency'] = getattr(self.instance, 'currency', 'INR') or 'INR'
        if 'document_type' in self.fields:
            self.fields['document_type'].required = False
        if 'access_level' in self.fields:
            self.fields['access_level'].required = False

    def clean_currency(self):
        val = self.cleaned_data.get('currency')
        if not val:
            if self.instance and self.instance.pk and self.instance.currency:
                return self.instance.currency
            return 'INR'
        return val

    def save(self, commit=True):
        """Handle new_tags creation before saving and preserve tags if not in form."""
        instance = super().save(commit=False)
        if commit:
            instance.save()
            if 'tags' in self.data:
                self.save_m2m()

            # Create and attach new tags
            new_tags_raw = self.cleaned_data.get('new_tags', '')
            if new_tags_raw:
                for tag_name in new_tags_raw.split(','):
                    tag_name = tag_name.strip()
                    if tag_name:
                        tag, _ = EDMSDocumentTag.objects.get_or_create(
                            name=tag_name,
                            defaults={'slug': slugify(tag_name)[:90]},
                        )
                        instance.tags.add(tag)
        else:
            if 'tags' in self.data:
                self.save_m2m = self._save_m2m
            else:
                self.save_m2m = lambda: None
        return instance


# ─── Version Upload Form ──────────────────────────────────────────────────────

class VersionUploadForm(forms.Form):
    """Upload a new version of an existing document."""
    file = forms.FileField(
        label='New Version File',
        widget=forms.ClearableFileInput(attrs={
            'class': 'hidden',
            'id':    'edms-version-file-input',
        }),
    )
    change_note = forms.CharField(
        label='Change Note',
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': TAILWIND_INPUT,
            'placeholder': 'Brief description of what changed in this version',
        }),
    )

    def clean_file(self):
        from edms.services.upload_service import UploadService
        f = self.cleaned_data['file']
        UploadService.validate(f)
        return f


# ─── Advanced Search Form ─────────────────────────────────────────────────────

class SearchForm(forms.Form):
    q               = forms.CharField(required=False, label='Search',
                                      widget=forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': 'Search documents…'}))
    category        = forms.ModelChoiceField(queryset=EDMSDocumentCategory.objects.filter(is_active=True),
                                             required=False, empty_label='All Categories',
                                             widget=forms.Select(attrs={'class': TAILWIND_SELECT}))
    department      = forms.ModelChoiceField(queryset=Department.objects.filter(is_active=True),
                                             required=False, empty_label='All Departments',
                                             widget=forms.Select(attrs={'class': TAILWIND_SELECT}))
    vendor          = forms.ModelChoiceField(queryset=EDMSVendor.objects.filter(is_active=True),
                                             required=False, empty_label='All Vendors',
                                             widget=forms.Select(attrs={'class': TAILWIND_SELECT}))
    document_type   = forms.ChoiceField(choices=[('', 'All Types')] + list(EDMSDocument.DOCUMENT_TYPE_CHOICES),
                                        required=False,
                                        widget=forms.Select(attrs={'class': TAILWIND_SELECT}))
    access_level    = forms.ChoiceField(choices=[('', 'All Access Levels')] + list(EDMSDocument.ACCESS_LEVEL_CHOICES),
                                        required=False,
                                        widget=forms.Select(attrs={'class': TAILWIND_SELECT}))
    approval_status = forms.ChoiceField(choices=[('', 'All Statuses')] + list(EDMSDocument.APPROVAL_STATUS_CHOICES),
                                        required=False,
                                        widget=forms.Select(attrs={'class': TAILWIND_SELECT}))
    file_extension  = forms.CharField(required=False, label='File Type',
                                      widget=forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': '.pdf'}))
    date_from       = forms.DateField(required=False, label='Doc Date From',
                                      widget=forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}))
    date_to         = forms.DateField(required=False, label='Doc Date To',
                                      widget=forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}))
    expiry_from     = forms.DateField(required=False,
                                      widget=forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}))
    expiry_to       = forms.DateField(required=False,
                                      widget=forms.DateInput(attrs={'class': TAILWIND_INPUT, 'type': 'date'}))
    amount_min      = forms.DecimalField(required=False, min_value=0,
                                         widget=forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}))
    amount_max      = forms.DecimalField(required=False, min_value=0,
                                         widget=forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}))
    sort            = forms.ChoiceField(
        required=False,
        choices=[
            ('-created_at',  'Newest First'),
            ('created_at',   'Oldest First'),
            ('title',        'Title A–Z'),
            ('-title',       'Title Z–A'),
            ('expiry_date',  'Expiry (soonest)'),
            ('-expiry_date', 'Expiry (latest)'),
            ('-file_size',   'Largest First'),
            ('file_size',    'Smallest First'),
        ],
        widget=forms.Select(attrs={'class': TAILWIND_SELECT}),
    )


# ─── Category Form ────────────────────────────────────────────────────────────

class CategoryForm(forms.ModelForm):
    class Meta:
        model  = EDMSDocumentCategory
        fields = ['name', 'description', 'icon', 'color', 'parent', 'is_active', 'order']
        widgets = {
            'name':        forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_AREA}),
            'icon':        forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': '📄'}),
            'color':       forms.TextInput(attrs={'class': TAILWIND_INPUT, 'type': 'color'}),
            'parent':      forms.Select(attrs={'class': TAILWIND_SELECT}),
            'is_active':   forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded text-blue-600'}),
            'order':       forms.NumberInput(attrs={'class': TAILWIND_INPUT}),
        }


# ─── Vendor Form ──────────────────────────────────────────────────────────────

class VendorForm(forms.ModelForm):
    class Meta:
        model  = EDMSVendor
        fields = ['name', 'contact_person', 'phone', 'email',
                  'gst_number', 'pan_number', 'address', 'is_active']
        widgets = {
            'name':           forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'contact_person': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'phone':          forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'email':          forms.EmailInput(attrs={'class': TAILWIND_INPUT}),
            'gst_number':     forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'pan_number':     forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'address':        forms.Textarea(attrs={'class': TAILWIND_AREA}),
            'is_active':      forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded text-blue-600'}),
        }


# ─── Company Profile Form ─────────────────────────────────────────────────────

class CompanyProfileForm(forms.ModelForm):
    class Meta:
        model  = EDMSCompanyProfile
        fields = [
            'company_name', 'gst_number', 'pan_number', 'cin',
            'udyam_number', 'registration_number', 'iso_number',
            'financial_year', 'turnover', 'address', 'website',
            'email', 'phone', 'logo',
        ]
        widgets = {
            'company_name':        forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'gst_number':          forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'pan_number':          forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'cin':                 forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'udyam_number':        forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'registration_number': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'iso_number':          forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'financial_year':      forms.TextInput(attrs={'class': TAILWIND_INPUT, 'placeholder': '2025-26'}),
            'turnover':            forms.NumberInput(attrs={'class': TAILWIND_INPUT, 'step': '0.01'}),
            'address':             forms.Textarea(attrs={'class': TAILWIND_AREA}),
            'website':             forms.URLInput(attrs={'class': TAILWIND_INPUT}),
            'email':               forms.EmailInput(attrs={'class': TAILWIND_INPUT}),
            'phone':               forms.TextInput(attrs={'class': TAILWIND_INPUT}),
        }


# ─── Department Form ──────────────────────────────────────────────────────────

class DepartmentForm(forms.ModelForm):
    class Meta:
        model  = Department
        fields = ['name', 'code', 'description', 'head', 'is_active']
        widgets = {
            'name':        forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'code':        forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.Textarea(attrs={'class': TAILWIND_AREA}),
            'head':        forms.Select(attrs={'class': TAILWIND_SELECT}),
            'is_active':   forms.CheckboxInput(attrs={'class': 'h-4 w-4 rounded text-blue-600'}),
        }


# ─── Saved Search Form ────────────────────────────────────────────────────────

class SavedSearchForm(forms.ModelForm):
    class Meta:
        model  = EDMSSavedSearch
        fields = ['name', 'description']
        widgets = {
            'name':        forms.TextInput(attrs={'class': TAILWIND_INPUT}),
            'description': forms.TextInput(attrs={'class': TAILWIND_INPUT}),
        }
