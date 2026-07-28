from django import forms
from .models import CompanyProfile, CompanyDocument

class CompanyProfileForm(forms.ModelForm):
    class Meta:
        model = CompanyProfile
        fields = ['name', 'gstin', 'pan', 'logo', 'signature', 'terms_conditions',
                  'invoice_prefix', 'quotation_prefix', 'po_prefix', 'challan_prefix',
                  'allow_document_deletion', 'admin_backup_email']

from .models import DocumentFolder

class DocumentFolderForm(forms.ModelForm):
    class Meta:
        model = DocumentFolder
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full bg-slate-800 border border-white/10 rounded-xl px-4 py-2 text-white placeholder-gray-400 focus:outline-none focus:border-blue-500 transition-colors', 'placeholder': 'e.g. Sales, Purchases'}),
        }

class CompanyDocumentForm(forms.ModelForm):
    class Meta:
        model = CompanyDocument
        fields = ['title', 'file']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full bg-slate-800 border border-white/10 rounded-xl px-4 py-2 text-white placeholder-gray-400 focus:outline-none focus:border-blue-500 transition-colors', 'placeholder': 'e.g. 2026 Tax Return'}),
            'file': forms.FileInput(attrs={'class': 'w-full bg-slate-800 border border-white/10 rounded-xl px-4 py-2 text-gray-300 focus:outline-none focus:border-blue-500 transition-colors file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-500/20 file:text-blue-400 hover:file:bg-blue-500/30'}),
        }
