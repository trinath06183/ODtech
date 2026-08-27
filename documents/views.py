from decimal import Decimal
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.db.models import Q, Sum, Count
from .models import Document, DocumentItem
from .services import DocumentService, PDFService, NumberingService
from core.decorators import require_permission
from inventory.models import Product
from contacts.models import Contact
from config.models import CompanyProfile
from django.views.decorators.http import require_POST
import json

# ─── Offline Document Generator ───────────────────────────────────────────────
def offline_document_view(request):
    """Standalone offline document generator - works without server connection via PWA cache."""
    return render(request, 'documents/document_offline.html')

# ─── Document Bundle Export (.oddoc) ──────────────────────────────────────────
import zipfile, io
from django.views.decorators.csrf import csrf_exempt

@require_permission('DOCUMENTS', 'read')
def export_document_bundle_view(request, document_id):
    """Export a document as a .oddoc bundle (zip containing JSON + meta)."""
    import json as _json
    doc = get_object_or_404(Document, id=document_id)
    items = list(doc.items.values(
        'id', 'name', 'description', 'quantity', 'unit', 'unit_price',
        'tax_rate', 'discount', 'total'
    ))
    payload = {
        'version': '1.0',
        'exported_at': doc.updated_at.isoformat() if doc.updated_at else '',
        'document': {
            'type': doc.type,
            'number': doc.number,
            'date': str(doc.date),
            'status': doc.status,
            'currency': doc.currency,
            'subtotal': str(doc.subtotal),
            'tax_total': str(doc.tax_total),
            'grand_total': str(doc.grand_total),
            'terms_and_conditions': doc.terms_and_conditions or '',
            'contact_name': doc.contact.name if doc.contact else '',
            'items': items,
        }
    }
    json_bytes = _json.dumps(payload, indent=2).encode('utf-8')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('document.json', json_bytes)
    buf.seek(0)
    safe_number = doc.number.replace('/', '-').replace(' ', '_')
    response = HttpResponse(buf.read(), content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{safe_number}.oddoc"'
    return response


@require_permission('DOCUMENTS', 'write')
def import_document_bundle_view(request):
    """Import a .oddoc bundle file and show the contained document data."""
    import json as _json
    if request.method != 'POST':
        return render(request, 'documents/document_list.html', {})

    uploaded = request.FILES.get('bundle_file')
    if not uploaded:
        messages.error(request, 'No file uploaded.')
        return redirect('document_list')

    try:
        buf = io.BytesIO(uploaded.read())
        with zipfile.ZipFile(buf, 'r') as zf:
            with zf.open('document.json') as jf:
                payload = _json.load(jf)
        messages.success(request, f"Bundle imported: {payload['document'].get('number', 'N/A')}")
    except Exception as e:
        messages.error(request, f'Failed to read bundle: {e}')

    return redirect('document_list')

# ─── Document List ────────────────────────────────────────────────────────────
@require_permission('DOCUMENTS', 'read')
def document_list(request):
    doc_types = request.GET.getlist('type')
    doc_types = [t for t in doc_types if t]
    query = request.GET.get('q', '').strip()
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    sort_by = request.GET.get('sort_by', '-id')

    qs = Document.objects.select_related('contact')
    if doc_types:
        qs = qs.filter(type__in=doc_types)

    if query:
        # Find categories of products matching the query to show similar products
        matching_categories = list(Product.objects.filter(
            Q(name__icontains=query) | Q(sku__icontains=query) | Q(description__icontains=query)
        ).exclude(category__isnull=True).exclude(category='').values_list('category', flat=True).distinct())

        qs = qs.filter(
            Q(number__icontains=query) |
            Q(contact__name__icontains=query) |
            Q(items__product__name__icontains=query) |
            Q(items__product__sku__icontains=query) |
            Q(items__product__description__icontains=query) |
            Q(items__name__icontains=query) |
            Q(items__description__icontains=query) |
            Q(items__product__category__in=matching_categories) |
            Q(items__product__category__icontains=query)
        ).distinct()

    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    allowed_sorts = ['date', '-date', 'grand_total', '-grand_total', '-id', 'type', '-type', 'contact__name', '-contact__name', 'status', '-status']
    if sort_by not in allowed_sorts:
        sort_by = '-id'
    qs = qs.order_by(sort_by)

    type_counts = dict(Document.objects.values('type').annotate(c=Count('id')).values_list('type', 'c'))

    stats = [
        {'type': 'QTN', 'label': 'Quotations',        'icon': '📋', 'count': type_counts.get('QTN', 0)},
        {'type': 'PRO', 'label': 'Proforma Invoices', 'icon': '📄', 'count': type_counts.get('PRO', 0)},
        {'type': 'INV', 'label': 'Invoices',          'icon': '🧾', 'count': type_counts.get('INV', 0)},
        {'type': 'PO',  'label': 'Purchase Orders',   'icon': '🛒', 'count': type_counts.get('PO', 0)},
        {'type': 'CHL', 'label': 'Challans',          'icon': '🚚', 'count': type_counts.get('CHL', 0)},
        {'type': 'DBN', 'label': 'Debit Notes',       'icon': '➖', 'count': type_counts.get('DBN', 0)},
        {'type': 'CRN', 'label': 'Credit Notes',      'icon': '➕', 'count': type_counts.get('CRN', 0)},
    ]
    filters = [
        {'type': 'QTN', 'label': 'Quotations'},
        {'type': 'PRO', 'label': 'Proforma Invoices'},
        {'type': 'INV', 'label': 'Invoices'},
        {'type': 'PO',  'label': 'Purchase Orders'},
        {'type': 'CHL', 'label': 'Challans'},
        {'type': 'DBN', 'label': 'Debit Notes'},
        {'type': 'CRN', 'label': 'Credit Notes'},
    ]

    # Suggestions for autocomplete
    recent_doc_numbers = list(Document.objects.values_list('number', flat=True).order_by('-id')[:10])
    recent_customer_names = list(Contact.objects.filter(contact_type__in=['Customer', 'Both']).values_list('name', flat=True).order_by('name')[:10])
    recent_product_names = list(Product.objects.values_list('name', flat=True).order_by('name')[:10])
    suggestions = sorted(list(set(recent_doc_numbers + recent_customer_names + recent_product_names)))

    company = CompanyProfile.objects.first()
    page_num = request.GET.get('page', 1)
    total_count = qs.count()
    try:
        total_sum = qs.aggregate(t=Sum('grand_total'))['t'] or Decimal('0')
    except Exception:
        total_sum = Decimal('0')

    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(page_num)

    # AJAX request — return only rows HTML + pagination metadata
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        rows_html = render_to_string(
            'documents/partials/document_rows.html',
            {'documents': page_obj, 'company': company, 'request': request},
            request=request,
        )
        return JsonResponse({
            'html': rows_html,
            'has_next': page_obj.has_next(),
            'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
        })

    return render(request, 'documents/document_list.html', {
        'documents': page_obj,
        'total_count': total_count,
        'total_sum': total_sum,
        'stats': stats,
        'filters': filters,
        'current_types': doc_types,
        'query': query,
        'date_from': date_from,
        'date_to': date_to,
        'sort_by': sort_by,
        'suggestions': suggestions,
        'company': company,
        'has_next': page_obj.has_next(),
        'next_page': 2 if page_obj.has_next() else '',
    })


# ─── Preview (wrapper UI page) ────────────────────────────────────────────────
@require_permission('DOCUMENTS', 'read')
def document_preview(request, document_id):
    doc = get_object_or_404(
        Document.objects.select_related('contact', 'source_document')
                        .prefetch_related('items__product', 'converted_documents'),
        id=document_id,
    )
    full_html = PDFService.render_html(doc, request=request)

    # Extract only the <body> content so we don't embed a full HTML doc inside the ERP page
    import re
    body_match = re.search(r'<body[^>]*>(.*?)</body>', full_html, re.DOTALL)
    # Also extract <style> from head so document styles are preserved
    style_match = re.findall(r'<style[^>]*>(.*?)</style>', full_html, re.DOTALL)
    style_block = '<style>' + '\n'.join(style_match) + '</style>' if style_match else ''
    preview_html = style_block + (body_match.group(1) if body_match else full_html)

    total_paid = doc.amount_paid
    balance_due = doc.balance_due

    # ── Previous / Next navigation (same doc type, ordered by id) ────────────
    prev_doc = Document.objects.filter(type=doc.type, id__lt=doc.id).order_by('-id').first()
    next_doc = Document.objects.filter(type=doc.type, id__gt=doc.id).order_by('id').first()

    linked_documents = doc.get_linked_documents()
    all_linked_payments = doc.payments_list
    total_paid_all = doc.amount_paid

    return render(request, 'documents/document_preview.html', {
        'doc': doc,
        'preview_html': preview_html,
        'total_paid': total_paid,
        'balance_due': balance_due,
        'document_types': Document.DOCUMENT_TYPES,
        'prev_doc': prev_doc,
        'next_doc': next_doc,
        'linked_documents': linked_documents,
        'all_linked_payments': all_linked_payments,
        'total_paid_all': total_paid_all,
    })


# ─── HTML Preview (raw doc HTML inside iframe) ────────────────────────────────
@require_permission('DOCUMENTS', 'read')
def document_html_preview(request, document_id):
    doc = get_object_or_404(Document, id=document_id)
    return HttpResponse(PDFService.render_html(doc, request=request))


# ─── Document Preview Data (JSON for sidebar preview card) ────────────────────
@require_permission('DOCUMENTS', 'read')
def document_preview_data(request, document_id):
    doc = get_object_or_404(Document, id=document_id)
    items = []
    for item in doc.items.select_related('product').all():
        has_product = item.product is not None
        items.append({
            'name': item.product.name if has_product else (item.name or ''),
            'sku': item.product.sku if has_product else (getattr(item, 'part_number', '') or ''),
            'qty': float(item.quantity),
            'unit': item.unit or (item.product.unit if has_product else 'EA') or 'EA',
            'unit_price': float(item.unit_price),
            'tax_rate': float(item.tax_rate),
            'total': float(item.total),
        })
    data = {
        'id': doc.id,
        'number': doc.number,
        'type': doc.get_type_display(),
        'status': doc.status,
        'date': doc.date.strftime('%d %b %Y'),
        'customer': doc.contact.name,
        'subtotal': float(doc.subtotal),
        'tax_total': float(doc.tax_total),
        'grand_total': float(doc.grand_total),
        'items': items,
        'preview_url': f'/documents/{doc.id}/preview/',
        'pdf_url': f'/documents/{doc.id}/pdf/',
    }
    return JsonResponse(data)



# ─── PDF Generation ───────────────────────────────────────────────────────────
def generate_pdf(request, document_id):
    """
    Generate and serve document PDF.
    Accessible with authenticated user permission OR via cryptographically signed token.
    """
    token = request.GET.get('token')
    if token:
        from django.core.signing import Signer, BadSignature
        signer = Signer(salt="document-public-view-salt")
        try:
            signed_id = signer.unsign(token)
            if str(signed_id) != str(document_id):
                return HttpResponse("Invalid access token.", status=403)
        except BadSignature:
            return HttpResponse("Invalid or expired document link.", status=403)
    else:
        # Require user authentication and permission
        if not request.user.is_authenticated or not request.user.has_section_perm('DOCUMENTS', 'read'):
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())

    doc = get_object_or_404(Document, id=document_id)
    try:
        pdf_file = PDFService.render_pdf(doc, request=request)
        response = HttpResponse(pdf_file, content_type='application/pdf')
        
        # Format filename: QTN_2026_27_06_0243_KIIT.pdf
        safe_number = doc.number.replace('-', '_').replace('/', '_')
        safe_contact = str(doc.contact.name).replace(' ', '_')
        filename = f"{safe_number}_{safe_contact}.pdf"
        
        if request.GET.get('download') == '1':
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
        else:
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            
        return response
    except Exception as e:
        warning_msg = (
            "<div style='background:#fee2e2;color:#991b1b;padding:15px;text-align:center;"
            "font-family:sans-serif;border-bottom:2px solid #ef4444;margin-bottom:20px;'>"
            "<strong>PDF library unavailable:</strong> Showing HTML preview instead. "
            f"<br><small>{e}</small></div>"
        )
        return HttpResponse(warning_msg + PDFService.render_html(doc, request=request))


# ─── Public Customer Document View (Secure Signed Token / No Login Needed) ────
def public_document_view(request, token):
    """
    Publicly view/download a commercial document securely using a cryptographically signed token.
    Customers CANNOT change the URL number to view other documents.
    No login required for the customer.
    """
    from django.core.signing import Signer, BadSignature
    signer = Signer(salt="document-public-view-salt")
    try:
        doc_id = signer.unsign(token)
    except BadSignature:
        return HttpResponse("<h1>403 Forbidden</h1><p>Invalid or expired document link.</p>", status=403)

    doc = get_object_or_404(Document, id=doc_id)
    
    # If ?pdf=1 is requested, serve PDF directly
    if request.GET.get('pdf') == '1':
        return generate_pdf(request, doc.id)

    # Render branded public viewer page
    return render(request, 'documents/public_document_view.html', {
        'doc': doc,
        'token': token,
        'preview_html': PDFService.render_html(doc, request=request),
    })


# ─── Email Document API (Auto-Attaches PDF + Secure Link) ─────────────────────
@require_POST
@require_permission('DOCUMENTS', 'write')
def email_document_api(request, document_id):
    """
    Sends the commercial document directly to the client's email.
    Auto-attaches the rendered PDF and provides the secure token link.
    """
    import json
    from django.core.mail import EmailMultiAlternatives
    from django.conf import settings
    from config.models import CompanyProfile

    doc = get_object_or_404(Document, id=document_id)
    try:
        data = json.loads(request.body) if request.body else {}
    except Exception:
        data = {}

    recipient_email = (data.get('email') or (doc.contact.email if doc.contact else '')).strip()
    if not recipient_email:
        return JsonResponse({'success': False, 'error': 'Recipient email address is required.'}, status=400)

    company = CompanyProfile.objects.first()
    company_name = company.name if company else "ODtech Solutions"
    doc_type_name = doc.get_type_display()
    
    # Generate public secure token link
    token = doc.get_access_token()
    site_url = request.build_absolute_uri('/')[:-1]
    public_url = f"{site_url}/documents/v/{token}/"
    total_formatted = f"₹{doc.grand_total:,.2f}"

    subject = f"[{company_name}] {doc_type_name}: {doc.number}"

    # Plain text body
    text_body = f"""Dear {doc.contact.name},

Greetings from {company_name}! Please find the details of your {doc_type_name.lower()} attached:

• Document No: {doc.number}
• Total Amount: {total_formatted}

You can also view and download the official digital document online at:
{public_url}

The official PDF document has been attached to this email for your reference.
If you have any questions or require modifications, feel free to reply directly to this email.

Best Regards,
{company_name}
"""

    # Rich responsive HTML body
    html_body = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0f172a;font-family:'Segoe UI',Arial,sans-serif;color:#e2e8f0;">
<div style="max-width:600px;margin:32px auto;border-radius:16px;overflow:hidden;border:1px solid #1e293b;background:#111827;">
  <div style="background:linear-gradient(135deg,#1e3a5f,#1e293b);padding:28px 32px;">
    <div style="font-size:12px;font-weight:700;color:#818cf8;text-transform:uppercase;letter-spacing:1px;">{company_name}</div>
    <div style="font-size:24px;font-weight:800;color:#ffffff;margin-top:4px;">{doc_type_name} #{doc.number}</div>
  </div>

  <div style="padding:28px 32px;border-bottom:1px solid #1e293b;">
    <p style="font-size:15px;color:#cbd5e1;margin-top:0;">Dear <strong>{doc.contact.name}</strong>,</p>
    <p style="font-size:14px;color:#94a3b8;line-height:1.6;">
      Greetings from <strong>{company_name}</strong>! Please find your <strong>{doc_type_name.lower()}</strong> summary below:
    </p>

    <table width="100%" style="margin:20px 0;background:#1e293b;border-radius:12px;border-collapse:collapse;overflow:hidden;">
      <tr>
        <td style="padding:12px 18px;color:#94a3b8;font-size:13px;border-bottom:1px solid #334155;">Document Number</td>
        <td style="padding:12px 18px;color:#f8fafc;font-weight:700;font-size:13px;border-bottom:1px solid #334155;text-align:right;">{doc.number}</td>
      </tr>
      <tr>
        <td style="padding:12px 18px;color:#94a3b8;font-size:13px;border-bottom:1px solid #334155;">Date</td>
        <td style="padding:12px 18px;color:#f8fafc;font-weight:600;font-size:13px;border-bottom:1px solid #334155;text-align:right;">{doc.date.strftime('%d %b %Y') if doc.date else '—'}</td>
      </tr>
      <tr>
        <td style="padding:14px 18px;color:#e2e8f0;font-size:14px;font-weight:700;">Total Amount</td>
        <td style="padding:14px 18px;color:#34d399;font-weight:800;font-size:18px;text-align:right;">{total_formatted}</td>
      </tr>
    </table>

    <div style="text-align:center;margin:28px 0 16px;">
      <a href="{public_url}" style="display:inline-block;padding:12px 28px;background:#4f46e5;color:#ffffff;text-decoration:none;font-weight:700;font-size:14px;border-radius:10px;box-shadow:0 4px 14px rgba(79,70,229,0.4);">
        View & Download Document
      </a>
    </div>

    <p style="font-size:13px;color:#64748b;text-align:center;margin-bottom:0;">
      📎 The official PDF document is also attached directly to this email.
    </p>
  </div>

  <div style="padding:20px 32px;background:#0f172a;text-align:center;color:#475569;font-size:12px;">
    {company_name} &bull; Official Digital Commercial Document
  </div>
</div>
</body>
</html>"""

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient_email],
    )
    msg.attach_alternative(html_body, "text/html")

    # Render & Attach the PDF
    try:
        pdf_content = PDFService.render_pdf(doc, request=request)
        safe_number = doc.number.replace('-', '_').replace('/', '_')
        safe_contact = str(doc.contact.name).replace(' ', '_')
        pdf_filename = f"{safe_number}_{safe_contact}.pdf"
        msg.attach(pdf_filename, pdf_content, 'application/pdf')
    except Exception as pdf_err:
        logger.warning("email_document_api: Could not attach PDF: %s", pdf_err)

    try:
        msg.send(fail_silently=False)
        return JsonResponse({'success': True, 'message': f'Document successfully emailed to {recipient_email}.'})
    except Exception as err:
        logger.error("email_document_api: Failed to send email: %s", err, exc_info=True)
        return JsonResponse({'success': False, 'error': f'Failed to send email: {str(err)}'}, status=500)
@require_permission('DOCUMENTS', 'write')
def delete_document(request, document_id):
    company = CompanyProfile.objects.first()
    if company and not company.allow_document_deletion:
        messages.error(request, 'Document deletion is disabled in system settings.')
        return redirect('document_list')
        
    doc = get_object_or_404(Document, id=document_id)
    if request.method == 'POST':
        doc_number = doc.number
        doc.delete()
        messages.success(request, f'Document {doc_number} deleted successfully.')
        return redirect('document_list')
    # GET → confirmation
    return render(request, 'documents/document_confirm_delete.html', {'doc': doc, 'company': company})


# ─── Change Document Status (Admin / Accountant only) ─────────────────────────
@require_permission('DOCUMENTS', 'read')
def change_document_status(request, document_id):
    doc = get_object_or_404(Document, id=document_id)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status not in [c[0] for c in Document.STATUS_CHOICES]:
            messages.error(request, "Invalid status choice.")
        else:
            if new_status == 'Approved':
                DocumentService.approve_document(doc.id)
                messages.success(request, f"Document {doc.number} has been approved.")
            else:
                # If reverting from Approved, or changing to Cancelled, etc.
                doc.status = new_status
                doc.save(update_fields=['status', 'updated_at'])
                messages.success(request, f"Document {doc.number} status changed to {new_status}.")
        return redirect('document_preview', document_id=doc.id)
    return redirect('document_list')


@require_permission('DOCUMENTS', 'read')
def get_next_number_api(request):
    """Returns the next available n+1 document number for a given document type."""
    doc_type = request.GET.get('type', 'QTN')
    doc_id = request.GET.get('doc_id')
    doc_id = int(doc_id) if doc_id and doc_id.isdigit() else None
    next_num = NumberingService.generate_document_number(doc_type, exclude_doc_id=doc_id)
    return JsonResponse({'success': True, 'type': doc_type, 'next_number': next_num})


@require_permission('DOCUMENTS', 'read')
def get_po_items_api(request, document_id):
    """Returns PO items for stock receiving modal with already received & remaining quantities."""
    doc = get_object_or_404(Document, id=document_id)
    from inventory.models import StockTransaction
    from django.db.models import Sum

    items_data = []
    for item in doc.items.select_related('product'):
        ordered_qty = Decimal(str(item.quantity))
        
        # Calculate already received quantity for this product on this PO
        already_received = Decimal('0')
        if item.product_id:
            already_received = StockTransaction.objects.filter(
                reference_document=doc.number,
                product_id=item.product_id,
                transaction_type='IN'
            ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
            
        remaining_qty = max(Decimal('0'), ordered_qty - already_received)

        items_data.append({
            'item_id': item.id,
            'product_id': item.product_id,
            'name': item.name or (item.product.name if item.product else 'Unnamed Item'),
            'sku': item.product.sku if item.product else (item.part_number or ''),
            'unit': item.unit or (item.product.unit if item.product else 'Nos'),
            'ordered_qty': float(ordered_qty),
            'already_received_qty': float(already_received),
            'remaining_qty': float(remaining_qty),
            'current_stock': float(item.product.current_stock) if item.product else 0,
        })
    return JsonResponse({
        'success': True,
        'doc_number': doc.number,
        'doc_type': doc.type,
        'items': items_data
    })


@require_permission('DOCUMENTS', 'write')
def receive_po_items_api(request, document_id):
    """Receives selected items from a PO and increases inventory stock."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid HTTP method'})
    
    doc = get_object_or_404(Document, id=document_id)
    try:
        data = json.loads(request.body)
        received_items = data.get('received_items', [])
        remarks = (data.get('remarks') or '').strip() or f"Goods received for PO #{doc.number}"
        
        if not received_items:
            return JsonResponse({'success': False, 'error': 'Please select at least one item to receive.'})
            
        from inventory.services import StockService
        total_received = 0
        
        for r_item in received_items:
            product_id = r_item.get('product_id')
            try:
                received_qty = Decimal(str(r_item.get('received_qty', 0)))
            except Exception:
                received_qty = Decimal('0')
                
            if product_id and received_qty > 0:
                StockService.create_transaction(
                    product_id=product_id,
                    transaction_type='IN',
                    quantity=received_qty,
                    reference_document=doc.number,
                    remarks=remarks
                )
                total_received += 1
                
        if doc.status != 'Approved':
            doc.status = 'Approved'
            doc.save(update_fields=['status', 'updated_at'])
            
        return JsonResponse({
            'success': True,
            'message': f"Successfully received {total_received} item(s) and updated inventory stock!"
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# ─── Product Search API ───────────────────────────────────────────────────────
@require_permission('DOCUMENTS', 'read')
def search_products(request):
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse([], safe=False)
    from django.db.models import Q
    products = Product.objects.filter(
        Q(name__icontains=query) | Q(sku__icontains=query)
    ).order_by('name')[:15]
    data = [
        {
            'id': p.id,
            'name': p.name,
            'sku': getattr(p, 'sku', ''),
            'unit': getattr(p, 'unit', 'EA'),
            'price': str(p.selling_price) if hasattr(p, 'selling_price') else '0.00',
            'tax_rate': str(p.tax_rate),
            'hsn_code': p.hsn_code or '',
            'description': p.description or '',
            'warranty_months': getattr(p, 'warranty_months', 12) or 12,
        }
        for p in products
    ]
    return JsonResponse(data, safe=False)


# ─── Create / Edit Document ─────────────────────────────────────────────────────
def document_form(request, doc=None, default_type='QTN'):
    if request.method == 'POST':
        action = request.POST.get('action', 'save_as_new') # 'update' or 'save_as_new'
        contact_id = request.POST.get('contact')
        doc_type = request.POST.get('type', 'QTN')
        currency = request.POST.get('currency', 'INR').strip()
        terms_and_conditions = request.POST.get('terms_and_conditions')
        show_gst = request.POST.get('show_gst') in ('on', 'true', True)
        split_gst = request.POST.get('split_gst') in ('on', 'true', True)
        force_igst = request.POST.get('force_igst') in ('on', 'true', True)
        show_payment_summary = request.POST.get('show_payment_summary') in ('on', 'true', True)
        discount_type = request.POST.get('discount_type', 'none')
        discount_value = request.POST.get('discount_value', '0.00')
        payment_milestones = request.POST.get('payment_milestones')
        numbering_mode = request.POST.get('numbering_mode', 'auto')
        manual_number = request.POST.get('number', '').strip()
        po_reference_number = request.POST.get('po_reference_number', '').strip()
        po_date = request.POST.get('po_date', '').strip() or None
        invoice_date = request.POST.get('invoice_date', '').strip() or None
        place_of_supply = request.POST.get('place_of_supply', '21-Odisha').strip()
        enable_warranty = request.POST.get('enable_warranty') in ('on', 'true', True)
        shipping_address = request.POST.get('shipping_address', '').strip()
        shipping_name = request.POST.get('shipping_name', '').strip()
        bill_from_name = request.POST.get('bill_from_name', '').strip()
        bill_from_address = request.POST.get('bill_from_address', '').strip()
        bill_from_gstin = request.POST.get('bill_from_gstin', '').strip()
        ship_from_name = request.POST.get('ship_from_name', '').strip()
        ship_from_address = request.POST.get('ship_from_address', '').strip()
        ship_from_gstin = request.POST.get('ship_from_gstin', '').strip()
        repeat_header = request.POST.get('repeat_header') in ('on', 'true', True)
        
        # Transporter Details POST parameters (For Delivery Challans)
        transporter_details = request.POST.get('transporter_details', 'Local Transportation').strip()
        vehicle_number = request.POST.get('vehicle_number', '').strip()
        transport_doc_no = request.POST.get('transport_doc_no', '').strip()
        transport_doc_date = request.POST.get('transport_doc_date', '').strip() or None
        eway_bill = request.POST.get('eway_bill', '').strip()
        eway_bill_date = request.POST.get('eway_bill_date', '').strip() or None
        transport_reason = request.POST.get('transport_reason', 'Refilling only, No Commercial involvement.').strip()
        
        items_json = request.POST.get('items_json', '[]')
        table_columns_json = request.POST.get('table_columns', '{}')
        
        try:
            table_columns = json.loads(table_columns_json)
        except json.JSONDecodeError:
            table_columns = {}

        try:
            items = json.loads(items_json)
        except json.JSONDecodeError:
            items = []

        # Validate contact and items
        contact = None
        if contact_id:
            try:
                contact = Contact.objects.get(id=contact_id)
            except (Contact.DoesNotExist, ValueError):
                pass

        valid_items = [item for item in items if item.get("product_id") or item.get("name")]

        errors = []
        if not contact:
            errors.append("Please select a valid customer.")
        if not valid_items:
            errors.append("Please add at least one line item.")

        if numbering_mode == 'manual':
            if not manual_number:
                errors.append("Please enter a document number.")
            else:
                # Check uniqueness
                duplicate_qs = Document.objects.filter(number=manual_number)
                if action == 'update' and doc:
                    duplicate_qs = duplicate_qs.exclude(id=doc.id)
                if duplicate_qs.exists():
                    errors.append(f"Document number '{manual_number}' already exists. Please choose a unique number.")

        if errors:
            for error in errors:
                messages.error(request, error)

            class DummyContact:
                def __init__(self, id):
                    self.id = id

            class DummyDoc:
                def __init__(self):
                    import datetime
                    
                    def parse_date(d_str):
                        if not d_str:
                            return None
                        try:
                            return datetime.datetime.strptime(d_str, '%Y-%m-%d').date()
                        except ValueError:
                            return None
                            
                    self.type = doc_type
                    self.numbering_mode = numbering_mode
                    self.number = manual_number if numbering_mode == 'manual' else (doc.number if doc else 'DRAFT')
                    self.contact = contact if contact else DummyContact('')
                    self.discount_type = discount_type
                    self.discount_value = discount_value
                    self.split_gst = split_gst
                    self.show_gst = show_gst
                    self.terms_and_conditions = terms_and_conditions
                    self.payment_milestones = payment_milestones
                    self.table_columns = table_columns
                    self.po_reference_number = po_reference_number
                    self.po_date = parse_date(po_date)
                    self.date = parse_date(invoice_date)
                    self.place_of_supply = place_of_supply
                    self.enable_warranty = enable_warranty
                    self.shipping_address = shipping_address
                    self.shipping_name = shipping_name
                    self.repeat_header = repeat_header
                    self.transporter_details = transporter_details
                    self.vehicle_number = vehicle_number
                    self.transport_doc_no = transport_doc_no
                    self.transport_doc_date = parse_date(transport_doc_date)
                    self.eway_bill = eway_bill
                    self.eway_bill_date = parse_date(eway_bill_date)
                    self.transport_reason = transport_reason
                def get_type_display(self):
                    return dict(Document.DOCUMENT_TYPES).get(self.type, self.type)
                def __bool__(self):
                    return bool(action == 'update' and doc is not None)

            contacts = Contact.objects.filter(contact_type__in=['Customer', 'Both'])
            recent_docs = Document.objects.all().order_by('-id')[:5]
            company = CompanyProfile.objects.first()

            return render(request, 'documents/document_create.html', {
                'contacts': contacts,
                'recent_docs': recent_docs,
                'doc': DummyDoc(),
                'default_type': default_type,
                'existing_items_json': items_json,
                'table_columns_json': table_columns_json,
                'milestones_json': payment_milestones or "[]",
                'document_types': Document.DOCUMENT_TYPES,
                'company': company,
                'next_number': manual_number if numbering_mode == 'manual' else (doc.number if doc else NumberingService.generate_document_number(default_type)),
            })

        if action == 'update' and doc:
            target_doc = DocumentService.update_document(
                doc,
                doc_type,
                contact_id,
                items,
                currency=currency,
                terms_and_conditions=terms_and_conditions,
                show_gst=show_gst,
                split_gst=split_gst,
                discount_type=discount_type,
                discount_value=discount_value,
                payment_milestones=payment_milestones,
                numbering_mode=numbering_mode,
                number=manual_number if numbering_mode == 'manual' else None,
                table_columns=table_columns,
                po_reference_number=po_reference_number,
                po_date=po_date,
                invoice_date=invoice_date,
                place_of_supply=place_of_supply,
                enable_warranty=enable_warranty,
                shipping_address=shipping_address,
                shipping_name=shipping_name,
                bill_from_name=bill_from_name,
                bill_from_address=bill_from_address,
                bill_from_gstin=bill_from_gstin,
                ship_from_name=ship_from_name,
                ship_from_address=ship_from_address,
                ship_from_gstin=ship_from_gstin,
                repeat_header=repeat_header,
                force_igst=force_igst,
                show_payment_summary=show_payment_summary,
                transporter_details=transporter_details,
                vehicle_number=vehicle_number,
                transport_doc_no=transport_doc_no,
                transport_doc_date=transport_doc_date,
                eway_bill=eway_bill,
                eway_bill_date=eway_bill_date,
                transport_reason=transport_reason,
                created_by=request.user,
            )
        else:
            source_doc = None
            convert_from_id = request.GET.get('convert_from')
            if convert_from_id:
                source_doc = Document.objects.filter(id=convert_from_id).first()
                
            target_doc = DocumentService.create_document(
                doc_type,
                contact_id,
                items,
                currency=currency,
                terms_and_conditions=terms_and_conditions,
                show_gst=show_gst,
                split_gst=split_gst,
                discount_type=discount_type,
                discount_value=discount_value,
                payment_milestones=payment_milestones,
                numbering_mode=numbering_mode,
                number=manual_number if numbering_mode == 'manual' else None,
                table_columns=table_columns,
                po_reference_number=po_reference_number,
                po_date=po_date,
                invoice_date=invoice_date,
                source_document=source_doc,
                place_of_supply=place_of_supply,
                enable_warranty=enable_warranty,
                shipping_address=shipping_address,
                shipping_name=shipping_name,
                bill_from_name=bill_from_name,
                bill_from_address=bill_from_address,
                bill_from_gstin=bill_from_gstin,
                ship_from_name=ship_from_name,
                ship_from_address=ship_from_address,
                ship_from_gstin=ship_from_gstin,
                repeat_header=repeat_header,
                force_igst=force_igst,
                show_payment_summary=show_payment_summary,
                transporter_details=transporter_details,
                vehicle_number=vehicle_number,
                transport_doc_no=transport_doc_no,
                transport_doc_date=transport_doc_date,
                eway_bill=eway_bill,
                eway_bill_date=eway_bill_date,
                transport_reason=transport_reason,
                created_by=request.user,
            )

        # Optional payment tracking
        payment_amount = request.POST.get('payment_amount', '').strip()
        if payment_amount:
            try:
                amt = float(payment_amount)
                if amt > 0:
                    from payments.models import Payment
                    Payment.objects.create(
                        contact_id=contact_id,
                        document_ref=target_doc.number,
                        amount=amt,
                        payment_mode=request.POST.get('payment_mode', 'Cash'),
                        reference_number=request.POST.get('payment_reference', '').strip() or None,
                        notes=request.POST.get('payment_notes', '').strip() or None,
                    )
            except ValueError:
                pass

        # Redirect to preview page
        return redirect('document_preview', document_id=target_doc.id)

    is_conversion = False
    convert_from = request.GET.get('convert_from')
    target_type = request.GET.get('target_type', default_type)

    if convert_from and not request.method == 'POST':
        try:
            doc = Document.objects.get(id=convert_from)
            is_conversion = True
            default_type = target_type
        except Document.DoesNotExist:
            pass

    contacts = Contact.objects.filter(contact_type__in=['Customer', 'Both'])
    recent_docs = Document.objects.all().order_by('-id')[:5]
    
    # Pre-populate items if editing or converting
    existing_items = []
    if doc:
        for di in doc.items.all():
            gross = float(di.quantity) * float(di.unit_price)
            pct = round((float(di.discount) / gross * 100), 2) if gross > 0 else 0
            existing_items.append({
                'product_id': '' if (di.product and getattr(di.product, 'sku', '') == 'CUSTOM') else (di.product_id or ''),
                'name': di.name or (di.product.name if di.product else 'Custom Line Item'),
                'description': di.description or '',
                'part_number': di.part_number or '',
                'qty': float(di.quantity),
                'unit': di.unit or (di.product.unit if di.product else 'EA'),
                'rate': float(di.unit_price),
                'discount': float(di.discount),
                'discount_pct': pct,
                'tax': float(di.tax_rate),
                'total': float(di.total),
                'hsn_code': di.hsn_code or (di.product.hsn_code if di.product else ''),
                'serial_number': di.serial_number or '',
                'has_warranty': di.has_warranty,
                'model': di.model or '',
                'warranty_period': di.warranty_period or '',
                'warranty_start_date': di.warranty_start_date.strftime('%Y-%m-%d') if di.warranty_start_date else '',
            })
    else:
        source_order_id = request.GET.get('source_order')
        seeded = request.session.pop('seeded_quotation_items', None)
        if seeded:
            existing_items = seeded
        elif source_order_id and not request.method == 'POST':
            try:
                from tracker.models import Order
                source_order = Order.objects.prefetch_related('products').get(id=source_order_id)
                selected_prod_ids = request.GET.get('product_ids', '').strip()
                selected_set = set(selected_prod_ids.split(',')) if selected_prod_ids else None
                
                # Check for custom dispatch quantities encoded in query (e.g. qty_PROD_ID=5)
                for prod in source_order.products.all():
                    if selected_set and str(prod.id) not in selected_set:
                        continue
                    
                    custom_qty_val = request.GET.get(f'qty_{prod.id}')
                    if custom_qty_val:
                        try:
                            qty = float(custom_qty_val)
                        except Exception:
                            qty = float(prod.quantity) if prod.quantity else 1.0
                    else:
                        qty = float(prod.quantity) if prod.quantity else 1.0

                    rate = float(prod.selling_price_ex_gst) if prod.selling_price_ex_gst else 0.0
                    tax = float(prod.gst_percentage) if prod.gst_percentage else 18.0
                    
                    existing_items.append({
                        'product_id': '',
                        'name': prod.item_name,
                        'description': prod.description or '',
                        'part_number': '',
                        'qty': qty,
                        'unit': prod.uom or 'Pcs',
                        'rate': rate,
                        'discount': 0.0,
                        'discount_pct': 0.0,
                        'tax': tax,
                        'total': qty * rate,
                        'hsn_code': '',
                        'serial_number': '',
                        'has_warranty': False,
                        'model': prod.make_or_model or '',
                        'warranty_period': '',
                        'warranty_start_date': '',
                    })
            except Exception:
                pass

        if not existing_items:
            existing_items = [{
                'product_id': '',
                'name': '',
                'description': '',
                'part_number': '',
                'qty': 1,
                'unit': 'EA',
                'rate': 0.0,
                'discount': 0.0,
                'discount_pct': 0.0,
                'tax': 18.0,
                'total': 0.0,
                'hsn_code': '',
                'serial_number': '',
                'has_warranty': False,
                'model': '',
                'warranty_period': '',
                'warranty_start_date': '',
            }]

    last_doc_settings_json = "null"
    if doc:
        if doc.table_columns:
            table_columns_json = json.dumps(doc.table_columns)
        else:
            table_columns_json = "null"
    else:
        last_doc = Document.objects.filter(type=default_type).order_by('-id').first()
        if last_doc:
            table_columns_json = json.dumps(last_doc.table_columns) if last_doc.table_columns else "null"
            last_doc_settings = {
                'show_gst': last_doc.show_gst,
                'split_gst': last_doc.split_gst,
                'place_of_supply': last_doc.place_of_supply,
                'numbering_mode': last_doc.numbering_mode,
                'discount_type': last_doc.discount_type,
                'discount_value': float(last_doc.discount_value),
                'terms_and_conditions': last_doc.terms_and_conditions,
                'enable_warranty': last_doc.enable_warranty,
                'repeat_header': last_doc.repeat_header,
                'show_payment_summary': last_doc.show_payment_summary,
                'currency': last_doc.currency,
            }
            last_doc_settings_json = json.dumps(last_doc_settings)
        else:
            table_columns_json = "null"
            # ── Fallback to company-level defaults when no prior document exists ──
            try:
                _co = CompanyProfile.objects.first()
                if _co:
                    last_doc_settings = {
                        'show_gst': _co.gst_enabled,
                        'split_gst': False,
                        'place_of_supply': '21-Odisha',
                        'numbering_mode': 'auto',
                        'discount_type': 'none',
                        'discount_value': 0.0,
                        'terms_and_conditions': None,
                        'enable_warranty': False,
                        'repeat_header': False,
                        'show_payment_summary': True,
                        'currency': _co.default_currency or 'INR',
                    }
                    last_doc_settings_json = json.dumps(last_doc_settings)
            except Exception:
                pass

    if is_conversion:
        next_number = NumberingService.generate_document_number(target_type)
    else:
        next_number = doc.number if doc else NumberingService.generate_document_number(default_type)
    
    milestones_json = "[]"
    if doc and doc.payment_milestones:
        try:
            parsed = json.loads(doc.payment_milestones)
            while isinstance(parsed, str):
                parsed = json.loads(parsed)
            milestones_json = json.dumps(parsed)
        except Exception:
            milestones_json = "[]"

    company = CompanyProfile.objects.first()

    return render(request, 'documents/document_create.html', {
        'contacts': contacts,
        'recent_docs': recent_docs,
        'doc': doc,
        'is_conversion': is_conversion,
        'default_type': default_type,
        'existing_items_json': json.dumps(existing_items),
        'table_columns_json': table_columns_json,
        'last_doc_settings_json': last_doc_settings_json,
        'milestones_json': milestones_json,
        'document_types': Document.DOCUMENT_TYPES,
        'company': company,
        'next_number': next_number,
        'currency_choices': Document.CURRENCY_CHOICES,
    })

@require_permission('DOCUMENTS', 'write')
def create_document(request):
    return document_form(request, default_type='QTN')

@require_permission('DOCUMENTS', 'write')
def create_quotation(request):
    return document_form(request, default_type='QTN')

@require_permission('DOCUMENTS', 'write')
def create_invoice(request):
    return document_form(request, default_type='INV')

@require_permission('DOCUMENTS', 'write')
def edit_document(request, document_id):
    doc = get_object_or_404(Document, id=document_id)
    return document_form(request, doc)

# ─── Product Create API ───────────────────────────────────────────────────────
@require_permission('DOCUMENTS', 'write')
def create_product_api(request):
    if request.method == 'POST':
        try:
            import re, uuid
            data = json.loads(request.body)
            name = (data.get('name') or '').strip()
            if not name:
                return JsonResponse({'success': False, 'error': 'Product name is required'})

            sku = (data.get('sku') or '').strip()
            # Auto-generate a unique SKU if not provided
            if not sku:
                base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:20]
                suffix = uuid.uuid4().hex[:6].upper()
                sku = f"{base}-{suffix}"
                # Ensure uniqueness (extremely unlikely collision, but be safe)
                while Product.objects.filter(sku=sku).exists():
                    sku = f"{base}-{uuid.uuid4().hex[:6].upper()}"

            price            = data.get('price', 0) or 0
            tax_rate         = data.get('tax_rate', 18.0) or 18.0
            hsn_code         = (data.get('hsn_code') or '').strip() or None
            description      = (data.get('description') or '').strip() or None
            unit             = (data.get('unit') or 'Nos').strip() or 'Nos'
            warranty_months  = int(data.get('warranty_months') or 12)

            product = Product.objects.create(
                name=name,
                sku=sku,
                selling_price=price,
                tax_rate=tax_rate,
                hsn_code=hsn_code,
                description=description,
                unit=unit,
                warranty_months=warranty_months,
            )

            return JsonResponse({
                'success': True,
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'sku': product.sku,
                    'unit': product.unit,
                    'price': str(product.selling_price),
                    'tax_rate': str(product.tax_rate),
                    'hsn_code': product.hsn_code or '',
                    'description': product.description or '',
                    'warranty_months': product.warranty_months,
                }
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request'})


# ─── All Products API (for Browse Modal) ─────────────────────────────────────
@require_permission('DOCUMENTS', 'write')
def all_products_api(request):
    query = request.GET.get('q', '').strip()
    products = Product.objects.all().order_by('name')
    if query:
        from django.db.models import Q
        products = products.filter(
            Q(name__icontains=query) | Q(sku__icontains=query) | Q(category__icontains=query)
        )
    data = [
        {
            'id': p.id,
            'name': p.name,
            'sku': getattr(p, 'sku', ''),
            'unit': getattr(p, 'unit', 'EA'),
            'category': getattr(p, 'category', '') or '',
            'price': str(p.selling_price) if hasattr(p, 'selling_price') else '0.00',
            'tax_rate': str(p.tax_rate),
            'stock': str(p.current_stock),
            'hsn_code': p.hsn_code or '',
            'description': p.description or '',
            'warranty_months': getattr(p, 'warranty_months', 12) or 12,
        }
        for p in products
    ]
    return JsonResponse(data, safe=False)


@require_permission('DOCUMENTS', 'write')
def cost_sheet(request):
    if request.method == 'POST':
        items_data = request.POST.get('items_json')
        try:
            items = json.loads(items_data)
            quotation_items = []
            for item in items:
                tax_rate = 18.0
                product_id = item.get('product_id')
                if product_id:
                    try:
                        product = Product.objects.get(id=product_id)
                        tax_rate = float(product.tax_rate)
                    except Product.DoesNotExist:
                        pass
                rate = float(item.get('selling_price', 0))
                qty = float(item.get('qty', 1))
                
                hsn_val = product.hsn_code if product_id else ''
                quotation_items.append({
                    'product_id': product_id,
                    'name': item.get('name', ''),
                    'qty': qty,
                    'rate': rate,
                    'discount': 0.0,
                    'tax': tax_rate,
                    'total': qty * rate * (1 + tax_rate / 100.0),
                    'hsn_code': hsn_val,
                })
            
            request.session['seeded_quotation_items'] = quotation_items
            messages.success(request, "Cost sheet calculated successfully! Seeded quotation creation flow.")
            return redirect('create_quotation')
        except Exception as e:
            messages.error(request, f"Error processing cost sheet: {e}")
            
    products = Product.objects.all().order_by('name')
    return render(request, 'documents/cost_sheet.html', {
        'products': products,
    })

@require_POST
@require_permission('DOCUMENTS', 'write')
def send_to_tracker_api(request, document_id):
    try:
        from tracker.models import Order as TrackerOrder, Product as TrackerProduct
        doc = get_object_or_404(Document, id=document_id)
        data = json.loads(request.body)
        order_number = data.get('order_number', '').strip()
        customer_phone = data.get('customer_phone', '').strip()

        if not order_number or not customer_phone:
            return JsonResponse({'success': False, 'error': 'Order Number and Customer Phone are required.'})

        if TrackerOrder.objects.filter(order_number=order_number).exists():
            return JsonResponse({'success': False, 'error': f'Order Number "{order_number}" already exists in Tracking Dashboard.'})

        # Create Order
        tracker_order = TrackerOrder.objects.create(
            order_number=order_number,
            customer_name=doc.contact.name,
            customer_phone=customer_phone,
            created_by=request.user,
            remark=f"Imported from {doc.get_type_display()} {doc.number}"
        )

        # Create Products
        sl_no = 1
        for item in doc.items.all():
            TrackerProduct.objects.create(
                order=tracker_order,
                sl_no=sl_no,
                item_name=item.name or item.product.name or 'Unknown Product',
                make_or_model=item.model or item.part_number or '',
                description=item.description or '',
                quantity=item.quantity,
                uom=item.unit or 'Pcs',
                selling_price_ex_gst=item.unit_price,
                gst_percentage=item.tax_rate,
                selling_price_inc_gst=item.unit_price * (1 + item.tax_rate / 100),
                created_by=request.user
            )
            sl_no += 1

        from django.urls import reverse
        return JsonResponse({
            'success': True, 
            'url': reverse('tracker:order_detail', args=[tracker_order.id])
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


import csv
from django.http import HttpResponse

@require_permission('DOCUMENTS', 'read')
def document_export_csv(request):
    """Export documents list to CSV."""
    doc_types = request.GET.getlist('type')
    doc_types = [t for t in doc_types if t]
    query = request.GET.get('q', '').strip()
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    sort_by = request.GET.get('sort_by', '-id')
    
    docs = Document.objects.select_related('contact')
    
    if doc_types:
        docs = docs.filter(type__in=doc_types)

    if query:
        from django.db.models import Q
        
        matching_categories = list(Product.objects.filter(
            Q(name__icontains=query) | Q(sku__icontains=query) | Q(description__icontains=query)
        ).exclude(category__isnull=True).exclude(category='').values_list('category', flat=True).distinct())

        docs = docs.filter(
            Q(number__icontains=query) |
            Q(contact__name__icontains=query) |
            Q(items__product__name__icontains=query) |
            Q(items__product__sku__icontains=query) |
            Q(items__product__description__icontains=query) |
            Q(items__name__icontains=query) |
            Q(items__description__icontains=query) |
            Q(items__product__category__in=matching_categories) |
            Q(items__product__category__icontains=query)
        ).distinct()

    if date_from:
        docs = docs.filter(date__gte=date_from)
    if date_to:
        docs = docs.filter(date__lte=date_to)

    allowed_sorts = ['date', '-date', 'grand_total', '-grand_total', '-id', 'type', '-type', 'contact__name', '-contact__name', 'status', '-status']
    if sort_by not in allowed_sorts:
        sort_by = '-id'
    docs = docs.order_by(sort_by)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="documents_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Number', 'Type', 'Contact', 'Status', 'Taxable Value', 'Total Tax', 'Grand Total'])
    
    for doc in docs:
        writer.writerow([
            doc.date.strftime('%d-%b-%Y') if doc.date else '',
            doc.number,
            doc.get_type_display(),
            doc.contact.name if doc.contact else '',
            doc.status,
            doc.subtotal,
            doc.tax_total,
            doc.grand_total
        ])
        
    return response
