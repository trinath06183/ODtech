from django.contrib import messages
from django.shortcuts import redirect, render

from core.decorators import role_required
from .models import CompanyProfile


@role_required('Admin')
def settings_view(request):
    company = CompanyProfile.objects.first()

    if request.method == 'POST':
        name              = request.POST.get('name', '').strip()
        gstin             = request.POST.get('gstin', '').strip()
        pan               = request.POST.get('pan', '').strip()
        invoice_prefix    = request.POST.get('invoice_prefix', 'INV-').strip()
        quotation_prefix  = request.POST.get('quotation_prefix', 'QTN-').strip()
        po_prefix         = request.POST.get('po_prefix', 'PO-').strip()
        challan_prefix    = request.POST.get('challan_prefix', 'CHL-').strip()
        terms_conditions  = request.POST.get('terms_conditions', '').strip()
        doc_number_format = request.POST.get('doc_number_format', 'OD-{FY}-{MM}-{N}').strip()
        allow_document_deletion = request.POST.get('allow_document_deletion') == 'on'

        if not name:
            messages.error(request, 'Company name is required.')
        else:
            if company is None:
                company = CompanyProfile()
            company.name             = name
            company.gstin            = gstin or None
            company.pan              = pan or None
            company.invoice_prefix   = invoice_prefix or 'INV-'
            company.quotation_prefix = quotation_prefix or 'QTN-'
            company.po_prefix        = po_prefix or 'PO-'
            company.challan_prefix   = challan_prefix or 'CHL-'
            company.terms_conditions = terms_conditions or None
            company.allow_document_deletion = allow_document_deletion
            # Validate format value against allowed choices
            valid_formats = [c[0] for c in CompanyProfile.DOC_NUMBER_FORMAT_CHOICES]
            if doc_number_format in valid_formats:
                company.doc_number_format = doc_number_format
            company.save()
            messages.success(request, 'Company settings saved successfully.')
            return redirect('settings')

    prefix_fields = [
        ('invoice_prefix',   'Invoice',   'INV-', getattr(company, 'invoice_prefix',   'INV-') if company else 'INV-'),
        ('quotation_prefix', 'Quotation', 'QTN-', getattr(company, 'quotation_prefix', 'QTN-') if company else 'QTN-'),
        ('po_prefix',        'Purchase',  'PO-',  getattr(company, 'po_prefix',         'PO-')  if company else 'PO-'),
        ('challan_prefix',   'Challan',   'CHL-', getattr(company, 'challan_prefix',    'CHL-') if company else 'CHL-'),
    ]

    return render(request, 'config/settings.html', {
        'company':              company,
        'prefix_fields':        prefix_fields,
        'doc_number_formats':   CompanyProfile.DOC_NUMBER_FORMAT_CHOICES,
        'current_doc_format':   getattr(company, 'doc_number_format', 'OD-{FY}-{MM}-{N}') if company else 'OD-{FY}-{MM}-{N}',
    })
from django.shortcuts import get_object_or_404
from .models import CompanyDocument
from .forms import CompanyDocumentForm

from .models import DocumentFolder
from .forms import DocumentFolderForm

@role_required('Admin')
def company_docs_list(request):
    # Root level view
    folders = DocumentFolder.objects.filter(parent__isnull=True)
    documents = CompanyDocument.objects.filter(folder__isnull=True)
    return render(request, 'config/folder_list.html', {
        'folders': folders,
        'documents': documents,
        'current_folder': None
    })

@role_required('Admin')
def company_folder_view(request, pk):
    folder = get_object_or_404(DocumentFolder, pk=pk)
    folders = DocumentFolder.objects.filter(parent=folder)
    documents = CompanyDocument.objects.filter(folder=folder)
    return render(request, 'config/folder_list.html', {
        'folders': folders,
        'documents': documents,
        'current_folder': folder
    })

@role_required('Admin')
def company_folder_create(request, parent_pk=None):
    parent = get_object_or_404(DocumentFolder, pk=parent_pk) if parent_pk else None
    if request.method == 'POST':
        form = DocumentFolderForm(request.POST)
        if form.is_valid():
            folder = form.save(commit=False)
            folder.parent = parent
            folder.created_by = request.user
            folder.save()
            messages.success(request, 'Folder created.')
            return redirect('company_folder_view', pk=parent.pk) if parent else redirect('company_docs_list')
    else:
        form = DocumentFolderForm()
    return render(request, 'config/company_doc_form.html', {
        'form': form,
        'title': 'Create New Folder'
    })

@role_required('Admin')
def company_folder_delete(request, pk):
    folder = get_object_or_404(DocumentFolder, pk=pk)
    parent_pk = folder.parent.pk if folder.parent else None
    if request.method == 'POST':
        folder.delete()
        messages.success(request, 'Folder deleted.')
    return redirect('company_folder_view', pk=parent_pk) if parent_pk else redirect('company_docs_list')

@role_required('Admin')
def company_docs_upload(request, folder_pk=None):
    folder = get_object_or_404(DocumentFolder, pk=folder_pk) if folder_pk else None
    if request.method == 'POST':
        form = CompanyDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.folder = folder
            doc.uploaded_by = request.user
            doc.save()
            messages.success(request, 'Document uploaded successfully.')
            return redirect('company_folder_view', pk=folder.pk) if folder else redirect('company_docs_list')
    else:
        form = CompanyDocumentForm()
    return render(request, 'config/company_doc_form.html', {
        'form': form,
        'title': 'Upload Document to ' + (folder.name if folder else 'Root')
    })

@role_required('Admin')
def company_docs_delete(request, pk):
    doc = get_object_or_404(CompanyDocument, pk=pk)
    folder_pk = doc.folder.pk if doc.folder else None
    if request.method == 'POST':
        doc.delete()
        messages.success(request, 'Document deleted.')
    return redirect('company_folder_view', pk=folder_pk) if folder_pk else redirect('company_docs_list')
