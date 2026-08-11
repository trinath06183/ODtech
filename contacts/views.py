from core.decorators import require_permission
import json
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from core.decorators import login_required, role_required, require_permission
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


# ── GSTIN Auto-Fetch API ────────────────────────────────────────────────────────
STATE_CODES = {
    '01': '01-Jammu & Kashmir', '02': '02-Himachal Pradesh', '03': '03-Punjab', '04': '04-Chandigarh',
    '05': '05-Uttarakhand', '06': '06-Haryana', '07': '07-Delhi', '08': '08-Rajasthan', '09': '09-Uttar Pradesh',
    '10': '10-Bihar', '11': '11-Sikkim', '12': '12-Arunachal Pradesh', '13': '13-Nagaland', '14': '14-Manipur',
    '15': '15-Mizoram', '16': '16-Tripura', '17': '17-Meghalaya', '18': '18-Assam', '19': '19-West Bengal',
    '20': '20-Jharkhand', '21': '21-Odisha', '22': '22-Chhattisgarh', '23': '23-Madhya Pradesh', '24': '24-Gujarat',
    '26': '26-Dadra & Nagar Haveli and Daman & Diu', '27': '27-Maharashtra', '29': '29-Karnataka', '30': '30-Goa',
    '31': '31-Lakshadweep', '32': '32-Kerala', '33': '33-Tamil Nadu', '34': '34-Puducherry', '35': '35-Andaman & Nicobar Islands',
    '36': '36-Telangana', '37': '37-Andhra Pradesh', '38': '38-Ladakh'
}

def gstin_lookup_api(request):
    import os
    import urllib.request
    import urllib.parse
    import ssl

    gstin = request.GET.get('gstin', '').strip().upper()
    if not gstin or len(gstin) != 15:
        return JsonResponse({'success': False, 'error': 'GSTIN must be exactly 15 characters long.'})

    from core.validators import GSTIN_PATTERN
    if not GSTIN_PATTERN.match(gstin):
        return JsonResponse({'success': False, 'error': 'Invalid GSTIN format. Example: 21AAAC0000A1Z5'})

    state_code = gstin[:2]
    place_of_supply = STATE_CODES.get(state_code, f'{state_code}-Other')
    pan = gstin[2:12]

    # PAN Entity Type Mapping (4th char)
    pan_type_char = pan[3:4] if len(pan) >= 4 else ''
    pan_entity_map = {
        'C': 'Company / Pvt Ltd',
        'P': 'Individual / Proprietorship',
        'F': 'Partnership Firm',
        'H': 'HUF',
        'A': 'Association of Persons',
        'T': 'Trust',
        'G': 'Government Body',
        'L': 'Local Authority'
    }
    taxpayer_type = pan_entity_map.get(pan_type_char, 'Regular Taxpayer')

    legal_name = ''
    trade_name = ''
    address = ''
    status = 'Active'
    pincode = ''
    state_name = place_of_supply.split('-', 1)[-1] if '-' in place_of_supply else ''
    fetched = False

    # Create SSL context
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # Read API Key from CompanyProfile or .env
    import http.client as _http_client

    db_key = None
    try:
        from config.models import CompanyProfile
        c_obj = CompanyProfile.objects.first()
        if c_obj:
            db_key = c_obj.gst_api_key
    except Exception:
        pass

    gst_api_key = (db_key or os.environ.get('GST_API_KEY', '')).strip(' "\'')

    # ── Primary: GST Insights API (gst-insights-api.p.rapidapi.com) ──────────
    if gst_api_key and not fetched:
        try:
            conn = _http_client.HTTPSConnection("gst-insights-api.p.rapidapi.com", timeout=6)
            conn.request("GET", f"/getGSTDetailsUsingGST/{gstin}", headers={
                'x-rapidapi-key': gst_api_key,
                'x-rapidapi-host': 'gst-insights-api.p.rapidapi.com',
                'Content-Type': 'application/json'
            })
            res = conn.getresponse()
            raw = res.read().decode('utf-8')
            print(f"[GST Insights] Status={res.status}, Body={raw[:500]}")
            if res.status == 200:
                payload = json.loads(raw)

                # data field is a LIST — take first element
                d = payload
                if isinstance(payload, dict) and 'data' in payload:
                    inner = payload['data']
                    if isinstance(inner, list) and len(inner) > 0:
                        d = inner[0]       # first record
                    elif isinstance(inner, dict):
                        d = inner

                if isinstance(d, dict):
                    # Legal / Trade name
                    t_name = (d.get('tradeName') or d.get('tradeNam') or d.get('trade_name')
                              or d.get('businessName') or d.get('BusinessName') or '')
                    l_name = (d.get('legalName') or d.get('lgnm') or d.get('legal_name')
                              or d.get('LegalName') or d.get('name') or '')
                    st     = (d.get('status') or d.get('sts') or d.get('taxType') or 'Active')
                    ctb    = (d.get('taxType') or d.get('ctb') or d.get('taxpayer_type') or taxpayer_type)

                    # ── Address: GST Insights uses additionalAddress list OR pradr.addr ──
                    addr_str = ''
                    # Try additionalAddress first (richer data)
                    add_list = d.get('additionalAddress', [])
                    if isinstance(add_list, list) and len(add_list) > 0:
                        aobj = add_list[0]
                        if isinstance(aobj, dict):
                            a = aobj.get('address', aobj)
                        else:
                            a = {}
                    else:
                        # Fallback to pradr.addr or pradr
                        pradr = d.get('pradr', {})
                        a = pradr.get('addr', pradr) if isinstance(pradr, dict) else {}
                        if not a:
                            a = d.get('address', {})

                    if isinstance(a, str):
                        addr_str = a
                    elif isinstance(a, dict):
                        bno  = a.get('buildingNumber','') or a.get('bno','') or a.get('bnm','')
                        bnm  = a.get('buildingName','') or a.get('flno','')
                        st_v = a.get('street','') or a.get('st','')
                        loc  = a.get('location','') or a.get('locality','') or a.get('loc','')
                        lm   = a.get('landMark','') or a.get('landmark','')
                        dst  = a.get('district','') or a.get('dst','') or a.get('city','')
                        stcd = a.get('stateCode','') or a.get('state','') or a.get('stcd','') or state_name
                        pncd = a.get('pincode','') or a.get('pncd','') or a.get('pin','')
                        if pncd:
                            pincode = str(pncd)
                        parts = [p for p in [bno, bnm, st_v, loc, lm, dst, stcd,
                                             (f"PIN: {pncd}" if pncd else '')] if p]
                        addr_str = ', '.join(parts)

                    if l_name or t_name or addr_str:
                        legal_name    = str(l_name).strip()
                        trade_name    = str(t_name).strip()
                        status        = str(st).strip() or 'Active'
                        taxpayer_type = str(ctb).strip() or taxpayer_type
                        if addr_str:
                            address = str(addr_str).strip()
                        fetched = True
                        print(f"[GST Insights SUCCESS] Legal={legal_name}, Trade={trade_name}, Addr={address}")
            conn.close()
        except Exception as e:
            print(f"[GST Insights ERROR] {e}")

    # ── Fallback: gst-api2.p.rapidapi.com ────────────────────────────────────
    if gst_api_key and not fetched:
        try:
            conn2 = _http_client.HTTPSConnection("gst-api2.p.rapidapi.com", timeout=6)
            conn2.request("GET", f"/api/gst/{gstin}", headers={
                'x-rapidapi-key': gst_api_key,
                'x-rapidapi-host': 'gst-api2.p.rapidapi.com',
                'Content-Type': 'application/json'
            })
            res2 = conn2.getresponse()
            raw2 = res2.read().decode('utf-8')
            print(f"[GST API2] Status={res2.status}, Body={raw2[:300]}")
            if res2.status == 200:
                d2 = json.loads(raw2)
                for key in ('data', 'result', 'details'):
                    if isinstance(d2, dict) and key in d2 and isinstance(d2[key], dict):
                        d2 = d2[key]
                if isinstance(d2, dict):
                    t2 = d2.get('tradeNam') or d2.get('trade_name') or d2.get('tradeName') or ''
                    l2 = d2.get('lgnm') or d2.get('legal_name') or d2.get('legalName') or d2.get('name') or ''
                    a2_data = d2.get('pradr', {}).get('addr', {}) or d2.get('pradr', {}) or d2.get('address', '')
                    a2 = ''
                    if isinstance(a2_data, str):
                        a2 = a2_data
                    elif isinstance(a2_data, dict):
                        parts2 = [p for p in [
                            a2_data.get('bno',''), a2_data.get('st',''),
                            a2_data.get('loc',''), a2_data.get('dst',''),
                            a2_data.get('stcd', state_name),
                            f"PIN: {a2_data.get('pncd','')}" if a2_data.get('pncd') else ''
                        ] if p]
                        a2 = ', '.join(parts2)
                        if a2_data.get('pncd'):
                            pincode = str(a2_data['pncd'])
                    if t2 or l2 or a2:
                        trade_name = str(t2).strip()
                        legal_name = str(l2).strip()
                        if a2:
                            address = str(a2).strip()
                        fetched = True
            conn2.close()
        except Exception as e:
            print(f"[GST API2 ERROR] {e}")

    last_error_msg = '' if fetched else 'No data found from any provider.'

    display_name = trade_name or legal_name

    return JsonResponse({
        'success': True,
        'gstin': gstin,
        'pan': pan,
        'legal_name': legal_name,
        'trade_name': trade_name,
        'name': display_name,
        'status': status,
        'taxpayer_type': taxpayer_type,
        'address': address,
        'place_of_supply': place_of_supply,
        'state_name': state_name,
        'pincode': pincode,
        'fetched': fetched,
        'debug_error': last_error_msg
    })


# ── Contact List ────────────────────────────────────────────────────────────────
@require_permission('CONTACTS', 'read')
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
@require_permission('CONTACTS', 'write')
def contact_create(request):
    return _contact_form(request)


# ── Contact Edit ────────────────────────────────────────────────────────────────
@require_permission('CONTACTS', 'write')
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
@require_permission('CONTACTS', 'write')
def contact_delete(request, contact_id):
    contact = get_object_or_404(Contact, id=contact_id)
    if request.method == 'POST':
        name = contact.name
        contact.delete()
        messages.success(request, f'Contact "{name}" deleted.')
    return redirect('contact_list')


# ── Contact Detail / Ledger ─────────────────────────────────────────────────────
@require_permission('CONTACTS', 'read')
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
@require_permission('CONTACTS', 'write')
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


@require_permission('CONTACTS', 'write')
def vendor_quote_create(request):
    return _vendor_quote_form(request)


@require_permission('CONTACTS', 'write')
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


@require_permission('CONTACTS', 'write')
def vendor_quote_delete(request, quote_id):
    quote = get_object_or_404(VendorQuote, id=quote_id)
    if request.method == 'POST':
        quote.delete()
        messages.success(request, 'Vendor quote deleted successfully.')
    return redirect('vendor_quotes')

import csv
from django.http import HttpResponse

@require_permission('CONTACTS', 'read')
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
