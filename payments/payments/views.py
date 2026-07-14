from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum
from core.decorators import login_required, role_required
from contacts.models import Contact
from documents.models import Document
from .models import Payment


@login_required
def payment_list(request):
    payments = Payment.objects.select_related('contact', 'document').order_by('-date', '-id')
    total = payments.aggregate(t=Sum('amount'))['t'] or 0
    return render(request, 'payments/payment_list.html', {
        'payments': payments,
        'total': total,
    })


@role_required('Admin', 'Accountant')
def payment_create(request):
    contacts  = Contact.objects.all().order_by('name')
    documents = Document.objects.filter(type__in=['INV', 'PRO'], status='Approved').order_by('-date')

    # Pre-select contact or document if passed as query param
    preselect_contact = request.GET.get('contact', '')
    preselect_document = request.GET.get('document', '')

    if request.method == 'POST':
        contact_id = request.POST.get('contact')
        document_id = request.POST.get('document') or None
        amount = request.POST.get('amount', '').strip()
        payment_mode = request.POST.get('payment_mode', 'Cash')
        reference_number = request.POST.get('reference_number', '').strip() or None
        notes = request.POST.get('notes', '').strip() or None

        errors = []
        if not contact_id:
            errors.append('Please select a party.')
        if not amount:
            errors.append('Amount is required.')

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            Payment.objects.create(
                contact_id=contact_id,
                document_id=document_id,
                amount=amount,
                payment_mode=payment_mode,
                reference_number=reference_number,
                notes=notes,
            )
            messages.success(request, 'Payment recorded successfully.')
            
            # If we came from a document, go back to it
            if document_id:
                return redirect('document_preview', document_id=document_id)
            return redirect('payment_list')

    return render(request, 'payments/payment_form.html', {
        'contacts': contacts,
        'documents': documents,
        'payment_modes': Payment.PAYMENT_MODES,
        'preselect_contact': preselect_contact,
        'preselect_document': preselect_document,
    })


@role_required('Admin')
def payment_delete(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    if request.method == 'POST':
        payment.delete()
        messages.success(request, 'Payment deleted.')
    return redirect('payment_list')
