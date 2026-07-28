import json
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from core.decorators import login_required, role_required
from .models import Contact, Address, VendorQuote
from inventory.models import Product


# ── Quick-create API (used from document form) ─────────────────────────────────
def create_customer_api(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name')
            email = data.get('email', '')
            phone = data.get('phone', '')
            gstin = data.get('gstin', '')
            address = data.get('address', '')
            if not name:
                return JsonResponse({'error': 'Name is required'}, status=400)
            contact = Contact.objects.create(
                name=name, contact_type='Customer',
                email=email, phone=phone, gstin=gstin, address=address
            )
            return JsonResponse({'id': contact.id, 'name': contact.name, 'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid method'}, status=405)


# ── Contact List ────────────────────────────────────────────────────────────────
@login_required
def contact_list(request):
    contact_type = request.GET.get('type', '')
    query = request.GET.get('q', '').strip()
    page_num = request.GET.get('page', 1)

    from payments.models import Payment
    contacts = Contact.objects.annotate(
        payments_total=Sum('payments__amount')
    ).order_by('name')

    if contact_type:
        contacts = contacts.filter(contact_type=contact_type)
    if query:
        contacts = contacts.filter(
            Q(name__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query) |
            Q(gstin__icontains=query)
        )

    total_count = contacts.count()
    paginator = Paginator(contacts, 30)
    page_obj = paginator.get_page(page_num)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from django.template.loader import render_to_string
        rows_html = render_to_string(
            'contacts/partials/contact_rows.html',
            {'contact_data': page_obj, 'request': request},
            request=request,
        )
        return JsonResponse({
            'html': rows_html,
            'has_next': page_obj.has_next(),
            'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
        })

    return render(request, 'contacts/contact_list.html', {
        'contact_data': page_obj,
        'contact_type': contact_type,
        'query': query,
        'total_count': total_count,
        'has_next': page_obj.has_next(),
        'next_page': 2 if page_obj.has_next() else None,
    })


# ── Contact Create ──────────────────────────────────────────────────────────────
@role_required('Admin', 'Accountant')
def contact_create(request):
    return _contact_form(request)


# ── Contact Edit ────────────────────────────────────────────────────────────────
@role_required('Admin', 'Accountant')
def contact_edit(request, contact_id):
    contact = get_object_or_404(Contact, id=contact_id)
    return _contact_form(request, contact)


def _contact_form(request, contact=None):
    if request.method == 'POST':
        name         = request.POST.get('name', '').strip()
        contact_type = request.POST.get('contact_type', 'Customer')
        email        = request.POST.get('email', '').strip() or None
        phone        = request.POST.get('phone', '').strip() or None
        gstin        = request.POST.get('gstin', '').strip() or None
        pan          = request.POST.get('pan', '').strip() or None
        address_text = request.POST.get('address', '').strip() or None

        if not name:
            messages.error(request, 'Name is required.')
        else:
            if contact:
                contact.name = name
                contact.contact_type = contact_type
                contact.email = email
                contact.phone = phone
                contact.gstin = gstin
                contact.pan = pan
                contact.address = address_text
                contact.save()
                messages.success(request, f'Contact "{name}" updated.')
            else:
                contact = Contact.objects.create(
                    name=name, contact_type=contact_type,
                    email=email, phone=phone, gstin=gstin,
                    pan=pan, address=address_text,
                )
                messages.success(request, f'Contact "{name}" created.')
            return redirect('contact_list')

    return render(request, 'contacts/contact_form.html', {
        'contact': contact,
        'form_title': 'Edit Contact' if contact else 'New Contact',
    })


# ── Contact Delete ──────────────────────────────────────────────────────────────
@role_required('Admin')
def contact_delete(request, contact_id):
    contact = get_object_or_404(Contact, id=contact_id)
    if request.method == 'POST':
        name = contact.name
        contact.delete()
        messages.success(request, f'Contact "{name}" deleted.')
    return redirect('contact_list')


# ── Contact Detail / Ledger ─────────────────────────────────────────────────────
@login_required
def contact_detail(request, contact_id):
    contact = get_object_or_404(Contact, id=contact_id)
    documents = contact.documents.all().order_by('-date')
    payments  = contact.payments.all().order_by('-date')

    invoiced_total  = contact.documents.filter(
        type__in=['INV', 'PRO'], status='Approved').aggregate(t=Sum('grand_total'))['t'] or 0
    payments_total  = payments.aggregate(t=Sum('amount'))['t'] or 0
    outstanding     = invoiced_total - payments_total

    return render(request, 'contacts/contact_detail.html', {
        'contact': contact,
        'documents': documents,
        'payments': payments,
        'invoiced_total': invoiced_total,
        'payments_total': payments_total,
        'outstanding': outstanding,
    })


# ── Vendor Quotes ───────────────────────────────────────────────────────────────
@login_required
def vendor_quotes(request):
    product_id = request.GET.get('product', '')
    quotes = VendorQuote.objects.select_related('vendor', 'product').all()
    products = Product.objects.all().order_by('name')

    cheapest_quote_id = None
    if product_id:
        quotes = quotes.filter(product_id=product_id)
        cheapest = quotes.first()
        if cheapest:
            cheapest_quote_id = cheapest.id

    return render(request, 'contacts/vendor_quotes.html', {
        'quotes': quotes,
        'products': products,
        'selected_product_id': int(product_id) if product_id.isdigit() else '',
        'cheapest_quote_id': cheapest_quote_id,
    })


@role_required('Admin', 'Accountant')
def vendor_quote_create(request):
    return _vendor_quote_form(request)


@role_required('Admin', 'Accountant')
def vendor_quote_edit(request, quote_id):
    quote = get_object_or_404(VendorQuote, id=quote_id)
    return _vendor_quote_form(request, quote)


def _vendor_quote_form(request, quote=None):
    vendors  = Contact.objects.filter(contact_type__in=['Vendor', 'Both']).order_by('name')
    products = Product.objects.all().order_by('name')

    if request.method == 'POST':
        vendor_id     = request.POST.get('vendor')
        product_id    = request.POST.get('product')
        quoted_price  = request.POST.get('quoted_price')
        quote_date    = request.POST.get('quote_date')
        valid_until   = request.POST.get('valid_until') or None
        lead_time_days= request.POST.get('lead_time_days') or None
        notes         = request.POST.get('notes', '').strip() or None

        errors = []
        if not vendor_id:    errors.append('Vendor is required.')
        if not product_id:   errors.append('Product is required.')
        if not quoted_price: errors.append('Quoted price is required.')
        if not quote_date:   errors.append('Quote date is required.')

        if errors:
            for err in errors:
                messages.error(request, err)
        else:
            if quote:
                quote.vendor_id = vendor_id; quote.product_id = product_id
                quote.quoted_price = quoted_price; quote.quote_date = quote_date
                quote.valid_until = valid_until; quote.lead_time_days = lead_time_days
                quote.notes = notes
                quote.save()
                messages.success(request, 'Vendor quote updated successfully.')
            else:
                VendorQuote.objects.create(
                    vendor_id=vendor_id, product_id=product_id,
                    quoted_price=quoted_price, quote_date=quote_date,
                    valid_until=valid_until, lead_time_days=lead_time_days, notes=notes
                )
                messages.success(request, 'Vendor quote added successfully.')
            return redirect('vendor_quotes')

    return render(request, 'contacts/vendor_quote_form.html', {
        'quote': quote,
        'vendors': vendors,
        'products': products,
        'form_title': 'Edit Vendor Quote' if quote else 'New Vendor Quote',
    })


@role_required('Admin')
def vendor_quote_delete(request, quote_id):
    quote = get_object_or_404(VendorQuote, id=quote_id)
    if request.method == 'POST':
        quote.delete()
        messages.success(request, 'Vendor quote deleted successfully.')
    return redirect('vendor_quotes')

import csv
from django.http import HttpResponse

@login_required
def contact_export_csv(request):
    """Export contacts list to CSV."""
    contact_type = request.GET.get('type', 'All')
    query = request.GET.get('q', '').strip()
    
    contacts = Contact.objects.all().order_by('name')
    if contact_type != 'All':
        contacts = contacts.filter(contact_type=contact_type)
    if query:
        contacts = contacts.filter(
            Q(name__icontains=query) |
            Q(email__icontains=query) |
            Q(phone__icontains=query) |
            Q(company_name__icontains=query)
        )
        
    from django.db.models import Sum
    contacts = contacts.annotate(payments_total=Sum('payments__amount'))

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="contacts_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Name', 'Company', 'Type', 'Email', 'Phone', 'GSTIN', 'Total Received/Paid'])
    
    for c in contacts:
        writer.writerow([
            c.name,
            c.company_name or '',
            c.contact_type,
            c.email or '',
            c.phone or '',
            c.gstin or '',
            c.payments_total or 0
        ])
        
    return response
