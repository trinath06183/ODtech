from decimal import Decimal
from core.decorators import require_permission
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.db.models import Q, Value, DecimalField
from django.db.models.functions import Coalesce
from django.db.models import Sum
from core.decorators import login_required, role_required, require_permission
from .models import Product, StockTransaction


# ─── Product List ─────────────────────────────────────────────────────────────
@require_permission('INVENTORY', 'read')
def inventory_list(request):
    query = request.GET.get('q', '').strip()
    page_num = request.GET.get('page', 1)

    # Annotate stock in one query (avoids N+1)
    products_qs = Product.objects.annotate(
        annotated_stock=Coalesce(
            Sum('stock_transactions__quantity'),
            Value(0),
            output_field=DecimalField()
        )
    ).order_by('name')

    if query:
        products_qs = products_qs.filter(
            Q(name__icontains=query) |
            Q(sku__icontains=query) |
            Q(brand__icontains=query) |
            Q(category__icontains=query)
        ).distinct()

    # Suggestions for autocomplete
    product_names = list(Product.objects.values_list('name', flat=True).order_by('name')[:10])
    product_skus = list(Product.objects.values_list('sku', flat=True).order_by('sku')[:10])
    product_brands = list(Product.objects.exclude(brand__isnull=True).exclude(brand='').values_list('brand', flat=True).order_by('brand')[:10])
    product_categories = list(Product.objects.exclude(category__isnull=True).exclude(category='').values_list('category', flat=True).order_by('category')[:10])
    suggestions = sorted(list(set(product_names + product_skus + product_brands + product_categories)))

    # Low stock count: items where stock < reorder_level (single query using F)
    from django.db.models import F
    low_stock_count = Product.objects.annotate(
        s=Coalesce(Sum('stock_transactions__quantity'), Value(0), output_field=DecimalField())
    ).filter(reorder_level__gt=0, s__lt=F('reorder_level')).count()

    total_count = products_qs.count()

    paginator = Paginator(products_qs, 30)
    page_obj = paginator.get_page(page_num)

    # AJAX request — return only rows HTML + pagination metadata
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        rows_html = render_to_string(
            'inventory/partials/product_rows.html',
            {'products': page_obj, 'request': request},
            request=request,
        )
        return JsonResponse({
            'html': rows_html,
            'has_next': page_obj.has_next(),
            'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
        })

    return render(request, 'inventory/inventory_list.html', {
        'products': page_obj,
        'total_count': total_count,
        'query': query,
        'suggestions': suggestions[:15],
        'low_stock_count': low_stock_count,
        'has_next': page_obj.has_next(),
        'next_page': 2 if page_obj.has_next() else None,
    })


# ─── Product Create (Admin only) ──────────────────────────────────────────────
@require_permission('INVENTORY', 'write')
def product_create(request):
    next_url = request.POST.get('next') or request.GET.get('next', '').strip()
    if request.method == 'POST':
        name           = request.POST.get('name', '').strip()
        sku            = request.POST.get('sku', '').strip()
        hsn_code       = request.POST.get('hsn_code', '').strip()
        tax_rate       = request.POST.get('tax_rate', '18.00').strip()
        selling_price  = request.POST.get('selling_price', '0.00').strip()
        purchase_price = request.POST.get('purchase_price', '0.00').strip()
        unit           = request.POST.get('unit', 'Nos').strip()
        brand          = request.POST.get('brand', '').strip()
        category       = request.POST.get('category', '').strip()
        description    = request.POST.get('description', '').strip()
        warranty_months = request.POST.get('warranty_months', '12').strip()
        reorder_level  = request.POST.get('reorder_level', '0').strip()

        errors = []
        if not name:
            errors.append('Product name is required.')
        if not sku:
            errors.append('SKU is required.')
        elif Product.objects.filter(sku=sku).exists():
            errors.append(f'SKU "{sku}" already exists.')

        if errors:
            for e in errors:
                messages.error(request, e)
        else:
            product = Product.objects.create(
                name=name, sku=sku, hsn_code=hsn_code or None,
                tax_rate=tax_rate, selling_price=selling_price,
                purchase_price=purchase_price or '0.00',
                unit=unit, brand=brand or None,
                category=category or None,
                description=description or None,
                warranty_months=warranty_months or '12',
                reorder_level=reorder_level or '0',
            )
            
            from inventory.models import ProductDescription
            desc_titles = request.POST.getlist('desc_title[]')
            desc_contents = request.POST.getlist('desc_content[]')
            for title, content in zip(desc_titles, desc_contents):
                if content.strip():
                    ProductDescription.objects.create(
                        product=product,
                        title=title.strip() or None,
                        content=content.strip()
                    )

            messages.success(request, f'Product "{name}" created successfully.')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect('inventory_list')

    return render(request, 'inventory/product_form.html', {
        'form_title':   'Add New Product',
        'submit_label': 'Create Product',
        'next_url': next_url,
    })


# ─── Product Edit (Admin only) ────────────────────────────────────────────────
@require_permission('INVENTORY', 'write')
def product_edit(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    if request.method == 'POST':
        product.name           = request.POST.get('name', product.name).strip()
        product.hsn_code       = request.POST.get('hsn_code', '').strip() or None
        product.tax_rate       = request.POST.get('tax_rate', product.tax_rate)
        product.selling_price  = request.POST.get('selling_price', product.selling_price)
        product.purchase_price = request.POST.get('purchase_price', product.purchase_price) or '0.00'
        product.unit           = request.POST.get('unit', product.unit).strip()
        product.brand          = request.POST.get('brand', '').strip() or None
        product.category       = request.POST.get('category', '').strip() or None
        product.description    = request.POST.get('description', '').strip() or None
        product.warranty_months = request.POST.get('warranty_months', product.warranty_months) or '12'
        product.reorder_level  = request.POST.get('reorder_level', product.reorder_level) or '0'

        new_sku = request.POST.get('sku', '').strip()
        if new_sku and new_sku != product.sku:
            if Product.objects.filter(sku=new_sku).exclude(id=product.id).exists():
                messages.error(request, f'SKU "{new_sku}" is already used by another product.')
                next_url = request.POST.get('next') or request.GET.get('next', '').strip()
                return render(request, 'inventory/product_form.html', {
                    'form_title':   f'Edit Product — {product.name}',
                    'submit_label': 'Save Changes',
                    'product':      product,
                    'next_url':     next_url,
                })
            product.sku = new_sku

        product.save()

        from inventory.models import ProductDescription
        desc_ids = request.POST.getlist('desc_id[]')
        desc_titles = request.POST.getlist('desc_title[]')
        desc_contents = request.POST.getlist('desc_content[]')
        
        submitted_ids = []
        for d_id, title, content in zip(desc_ids, desc_titles, desc_contents):
            if not content.strip():
                continue
            if d_id and d_id.strip():
                try:
                    desc = ProductDescription.objects.get(id=d_id, product=product)
                    desc.title = title.strip() or None
                    desc.content = content.strip()
                    desc.save()
                    submitted_ids.append(desc.id)
                except ProductDescription.DoesNotExist:
                    pass
            else:
                desc = ProductDescription.objects.create(
                    product=product,
                    title=title.strip() or None,
                    content=content.strip()
                )
                submitted_ids.append(desc.id)
                
        product.additional_descriptions.exclude(id__in=submitted_ids).delete()

        messages.success(request, f'Product "{product.name}" updated successfully.')
        return redirect('inventory_list')

    from documents.models import DocumentItem
    linked_doc_items = DocumentItem.objects.filter(product=product).select_related('document', 'document__contact').order_by('-document__date')

    next_url = request.POST.get('next') or request.GET.get('next', '').strip()
    return render(request, 'inventory/product_form.html', {
        'form_title':   f'Edit Product — {product.name}',
        'submit_label': 'Save Changes',
        'product':      product,
        'linked_doc_items': linked_doc_items,
        'next_url':     next_url,
    })


# ─── Product Delete (Admin only) ──────────────────────────────────────────────
@require_permission('INVENTORY', 'write')
def product_delete(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    if request.method == 'POST':
        name = product.name
        # Delete product (Django ORM handles cascading deletion of linked stock transactions & items)
        product.delete()
        messages.success(request, f'Product "{name}" deleted successfully.')
        return redirect('inventory_list')

    # GET: confirmation page
    return render(request, 'inventory/product_confirm_delete.html', {'product': product})


# ─── Stock Adjustment (Admin only) ────────────────────────────────────────────
@require_permission('INVENTORY', 'write')
def adjust_stock(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    if request.method == 'POST':
        transaction_type     = request.POST.get('transaction_type')
        qty_str              = request.POST.get('quantity', '0').strip()
        batch_number         = request.POST.get('batch_number', '').strip() or None
        serial_number        = request.POST.get('serial_number', '').strip() or None
        reason               = request.POST.get('reason', '').strip() or None
        remarks              = request.POST.get('remarks', '').strip() or None
        adjustment_direction = request.POST.get('adjustment_direction', 'add')

        try:
            from decimal import Decimal
            quantity = Decimal(qty_str)
        except (ValueError, TypeError):
            messages.error(request, "Invalid quantity value.")
            return redirect('adjust_stock', product_id=product.id)

        if quantity <= 0:
            messages.error(request, "Quantity must be greater than zero.")
            return redirect('adjust_stock', product_id=product.id)

        # Map direction for ADJUSTMENT/OUT/IN
        if transaction_type == 'ADJUSTMENT' and adjustment_direction == 'reduce':
            quantity = -quantity
        elif transaction_type == 'OUT':
            quantity = -quantity

        # Save transaction
        from inventory.services import StockService
        StockService.create_transaction(
            product_id=product.id,
            transaction_type=transaction_type,
            quantity=quantity,
            batch_number=batch_number,
            serial_number=serial_number,
            reason=reason,
            remarks=remarks
        )
        messages.success(request, f"Manual stock transaction ({transaction_type}) created for {product.name}.")
        return redirect('inventory_list')

    return render(request, 'inventory/adjust_stock.html', {
        'product': product,
        'transaction_types': StockTransaction.TRANSACTION_TYPES,
    })


# ─── Warranty Tracker ─────────────────────────────────────────────────────────
@require_permission('INVENTORY', 'write')
def warranty_tracker(request):
    from documents.models import DocumentItem
    from django.db.models import Q
    from django.utils import timezone
    import datetime
    import calendar
    import re

    query = request.GET.get('q', '').strip()
    
    # Base query: Items with warranty checked, from approved documents
    items = DocumentItem.objects.filter(has_warranty=True, document__status='Approved').select_related('document', 'product', 'document__contact')
    
    # Exclude Custom Line Items and items without any warranty period defined
    items = items.exclude(product__sku__iexact='CUSTOM').exclude(warranty_period__isnull=True).exclude(warranty_period__exact='')
    
    if query:
        items = items.filter(
            Q(serial_number__icontains=query) |
            Q(document__number__icontains=query) |
            Q(product__sku__icontains=query) |
            Q(document__contact__name__icontains=query)
        )
        
    results = []
    now = timezone.now().date()
    
    def add_months(sourcedate, months):
        month = sourcedate.month - 1 + months
        year = int(sourcedate.year + month / 12)
        month = month % 12 + 1
        day = min(sourcedate.day, calendar.monthrange(year, month)[1])
        return datetime.date(year, month, day)
    
    for item in items:
        months = 0
        if item.warranty_period:
            match = re.search(r'(\d+)', str(item.warranty_period))
            if match:
                val = int(match.group(1))
                if 'year' in item.warranty_period.lower():
                    months = val * 12
                else:
                    months = val
                    
        start_date = item.warranty_start_date or item.document.date
        expiry_date = None
        is_active = False
        
        if start_date and months > 0:
            expiry_date = add_months(start_date, months)
            is_active = expiry_date >= now
            
        # Check if customer has registered it publicly
        is_registered = False
        if item.serial_number:
            from .models import WarrantyRegistration
            is_registered = WarrantyRegistration.objects.filter(serial_number__iexact=item.serial_number.strip()).exists()
            
        results.append({
            'item': item,
            'product': item.product,
            'document': item.document,
            'customer_name': item.document.contact.name if item.document.contact else 'Unknown',
            'invoice_date': start_date,
            'warranty_months': months,
            'expiry_date': expiry_date,
            'is_active': is_active,
            'is_registered': is_registered,
        })

    return render(request, 'inventory/warranty_tracker.html', {
        'query': query,
        'results': results,
    })

# ------------------------------------------------------------------------------
# WARRANTY PORTAL VIEWS
# ------------------------------------------------------------------------------

# --- Warranty Registration ----------------------------------------------------
def warranty_register(request):
    """Public: display and process the warranty registration form."""
    from .models import WarrantyRegistration

    from documents.models import Document, DocumentItem
    
    step = int(request.POST.get('step', 1))
    errors = []
    post = request.POST.copy()
    
    if request.method == 'POST':
        if step == 1:
            invoice_number = request.POST.get('invoice_number', '').strip()
            invoice_date = request.POST.get('invoice_date', '').strip()
            invoice_amount = request.POST.get('invoice_amount', '').strip()
            
            if not invoice_number: errors.append('Invoice number is required.')
            if not invoice_date: errors.append('Invoice date is required.')
            if not invoice_amount: errors.append('Invoice amount is required.')
            
            if not errors:
                try:
                    from decimal import Decimal
                    amount = Decimal(invoice_amount)
                    doc = Document.objects.filter(
                        number__iexact=invoice_number,
                        date=invoice_date,
                        grand_total=amount
                    ).first()
                    
                    if not doc:
                        errors.append('No matching invoice found. Please check your details.')
                    else:
                        step = 2
                except Exception:
                    errors.append('Invoice amount must be a valid number.')
                    
        elif step == 2:
            invoice_number = request.POST.get('invoice_number', '').strip()
            invoice_date = request.POST.get('invoice_date', '').strip()
            serial_number = request.POST.get('serial_number', '').strip()
            
            if not serial_number: errors.append('Serial number is required.')
            
            if not errors:
                doc = Document.objects.filter(number__iexact=invoice_number, date=invoice_date).first()
                if not doc:
                    errors.append('Invoice validation failed.')
                else:
                    item = DocumentItem.objects.filter(
                        document=doc,
                        has_warranty=True,
                        serial_number__icontains=serial_number
                    ).first()
                    
                    if not item:
                        errors.append('Serial number not found or does not have warranty on this invoice.')
                    else:
                        step = 3
                        
        elif step == 3:
            invoice_number = request.POST.get('invoice_number', '').strip()
            invoice_date = request.POST.get('invoice_date', '').strip()
            invoice_amount = request.POST.get('invoice_amount', '').strip()
            serial_number = request.POST.get('serial_number', '').strip()
            
            company_name = request.POST.get('company_name', '').strip()
            gst_number = request.POST.get('gst_number', '').strip() or None
            email = request.POST.get('email', '').strip()
            contact_number = request.POST.get('contact_number', '').strip()
            product_image = request.FILES.get('product_image')
            invoice_document = request.FILES.get('invoice_document')
            
            if not company_name: errors.append('Company / Customer name is required.')
            if not email: errors.append('Email address is required.')
            if not contact_number: errors.append('Contact number is required.')
            if not product_image: errors.append('Product image is required.')
            if not invoice_document: errors.append('Invoice document is required.')
            
            if not errors:
                WarrantyRegistration.objects.create(
                    invoice_number=invoice_number,
                    serial_number=serial_number,
                    invoice_date=invoice_date,
                    invoice_amount=invoice_amount,
                    company_name=company_name,
                    gst_number=gst_number,
                    email=email,
                    contact_number=contact_number,
                    product_image=product_image,
                    invoice_document=invoice_document,
                )
                return redirect('warranty_register_success')
                
    return render(request, 'inventory/warranty_register.html', {
        'step': step,
        'errors': errors,
        'post': post,
    })


def warranty_register_success(request):
    """Public: thank-you page after registration."""
    return render(request, 'inventory/warranty_register_success.html', {})


# --- Warranty Claim -----------------------------------------------------------
def warranty_claim(request):
    """
    Public: two-step warranty claim.
    Step 1 (POST with action=validate): verify 4 fields, store registration id in session.
    Step 2 (POST with action=submit):  save claim linked to validated registration.
    """
    from .models import WarrantyRegistration, WarrantyClaim
    from decimal import Decimal, InvalidOperation

    step1_error   = None
    step2_errors  = []
    validated_reg = None
    step2_open    = False

    # Check if Step 1 was already validated in this session
    session_reg_id = request.session.get('warranty_validated_id')
    if session_reg_id:
        try:
            validated_reg = WarrantyRegistration.objects.get(id=session_reg_id)
            step2_open = True
        except WarrantyRegistration.DoesNotExist:
            del request.session['warranty_validated_id']

    if request.method == 'POST':
        action = request.POST.get('action', '')

        # -- Step 1: Validate --------------------------------------------------
        if action == 'validate':
            serial_number  = request.POST.get('serial_number', '').strip()
            invoice_number = request.POST.get('invoice_number', '').strip()
            invoice_amount = request.POST.get('invoice_amount', '').strip()
            invoice_date   = request.POST.get('invoice_date', '').strip()

            try:
                amount = Decimal(invoice_amount) if invoice_amount else None
            except InvalidOperation:
                amount = None

            if not all([serial_number, invoice_number, invoice_amount, invoice_date, amount]):
                step1_error = 'All four fields are required and the amount must be a valid number.'
            else:
                try:
                    reg = WarrantyRegistration.objects.get(
                        serial_number__iexact=serial_number,
                        invoice_number__iexact=invoice_number,
                        invoice_amount=amount,
                        invoice_date=invoice_date,
                    )
                    request.session['warranty_validated_id'] = reg.id
                    validated_reg = reg
                    step2_open = True
                except WarrantyRegistration.DoesNotExist:
                    step1_error = 'Validation failed. Details do not match our records.'

        # -- Step 2: Submit Claim ----------------------------------------------
        elif action == 'submit':
            if not session_reg_id:
                step1_error = 'Session expired. Please complete Step 1 again.'
            else:
                try:
                    reg = WarrantyRegistration.objects.get(id=session_reg_id)
                except WarrantyRegistration.DoesNotExist:
                    step1_error = 'Registration not found. Please restart the process.'
                    reg = None

                if reg:
                    problem_description = request.POST.get('problem_description', '').strip()
                    if not problem_description:
                        step2_errors.append('Problem description is required.')
                        step2_open = True
                        validated_reg = reg
                    else:
                        claim = WarrantyClaim(
                            registration=reg,
                            problem_description=problem_description,
                        )
                        for field in ['attachment_1', 'attachment_2', 'attachment_3',
                                      'product_photo_1', 'product_photo_2']:
                            f = request.FILES.get(field)
                            if f:
                                setattr(claim, field, f)
                        claim.save()
                        # Clear session after successful claim
                        del request.session['warranty_validated_id']
                        return redirect('warranty_claim_success', claim_number=claim.claim_number)

    return render(request, 'inventory/warranty_claim.html', {
        'step1_error':   step1_error,
        'step2_errors':  step2_errors,
        'step2_open':    step2_open,
        'validated_reg': validated_reg,
    })


def warranty_claim_success(request, claim_number):
    """Public: confirmation page displaying the unique claim tracking number."""
    from .models import WarrantyClaim
    claim = get_object_or_404(WarrantyClaim, claim_number=claim_number)
    return render(request, 'inventory/warranty_claim_success.html', {'claim': claim})


def warranty_claim_status(request):
    """Public: enter a claim number to check its current status."""
    from .models import WarrantyClaim
    claim = None
    error = None
    query = request.GET.get('claim_number', '').strip().upper()

    if query:
        try:
            claim = WarrantyClaim.objects.select_related('registration').get(claim_number=query)
        except WarrantyClaim.DoesNotExist:
            error = f'No claim found with number \u201c{query}\u201d. Please check and try again.'

    # Build progress timeline for the template
    claim_steps = []
    if claim:
        all_steps = [
            ('Pending',   'Claim Submitted',     'Your claim has been received by ODtech.'),
            ('In Review', 'Under Review',         'Our team is reviewing your claim.'),
            ('Resolved',  'Claim Resolved',       'Your claim has been resolved.'),
        ]
        status_order = ['Pending', 'In Review', 'Resolved', 'Rejected']
        current_idx = status_order.index(claim.status) if claim.status in status_order else 0
        if claim.status == 'Rejected':
            all_steps.append(('Rejected', 'Claim Rejected', 'Unfortunately your claim could not be approved.'))
            current_idx = 3
        for i, (s, lbl, desc) in enumerate(all_steps):
            active = i <= current_idx
            claim_steps.append((s, lbl, desc, active))

    return render(request, 'inventory/warranty_status.html', {
        'claim': claim,
        'query': query,
        'error': error,
        'claim_steps': claim_steps,
    })



def warranty_claim_recover(request):
    """Public: recover claim tracking numbers based on registration details."""
    from .models import WarrantyRegistration, WarrantyClaim
    from decimal import Decimal, InvalidOperation

    error = None
    claims = []

    if request.method == 'POST':
        company_name   = request.POST.get('company_name', '').strip()
        serial_number  = request.POST.get('serial_number', '').strip()
        invoice_number = request.POST.get('invoice_number', '').strip()
        invoice_amount = request.POST.get('invoice_amount', '').strip()
        invoice_date   = request.POST.get('invoice_date', '').strip()

        try:
            amount = Decimal(invoice_amount) if invoice_amount else None
        except InvalidOperation:
            amount = None

        if not all([company_name, serial_number, invoice_number, invoice_amount, invoice_date, amount]):
            error = 'All fields are required and amount must be valid.'
        else:
            try:
                # Find the registration
                reg = WarrantyRegistration.objects.get(
                    company_name__iexact=company_name,
                    serial_number__iexact=serial_number,
                    invoice_number__iexact=invoice_number,
                    invoice_amount=amount,
                    invoice_date=invoice_date,
                )
                # Find claims
                claims = WarrantyClaim.objects.filter(registration=reg).order_by('-created_at')
                if not claims.exists():
                    error = 'Registration found, but no claims have been filed for it.'
            except WarrantyRegistration.DoesNotExist:
                error = 'No registration found matching these details. Please check and try again.'

    return render(request, 'inventory/warranty_claim_recover.html', {
        'error': error,
        'claims': claims,
        'post': request.POST,
    })

# --- Warranty Admin -----------------------------------------------------------
@require_permission('INVENTORY', 'read')
def warranty_admin_list(request):
    """Internal: list all registrations and claims for Admin/Accountant."""
    from .models import WarrantyRegistration, WarrantyClaim

    tab = request.GET.get('tab', 'registrations')
    status_filter = request.GET.get('status', '')

    registrations = WarrantyRegistration.objects.order_by('-created_at')
    claims_qs = WarrantyClaim.objects.select_related('registration').order_by('-created_at')
    if status_filter:
        claims_qs = claims_qs.filter(status=status_filter)

    return render(request, 'inventory/warranty_admin_list.html', {
        'registrations':  registrations,
        'claims':         claims_qs,
        'tab':            tab,
        'status_filter':  status_filter,
        'status_choices': WarrantyClaim.STATUS_CHOICES,
    })


@require_permission('INVENTORY', 'read')
def warranty_admin_update_status(request, claim_id):
    """Internal: update the status of a warranty claim."""
    from .models import WarrantyClaim
    if request.method == 'POST':
        claim = get_object_or_404(WarrantyClaim, id=claim_id)
        new_status = request.POST.get('status', '').strip()
        status_reason = request.POST.get('status_reason', '').strip()
        valid_statuses = [s[0] for s in WarrantyClaim.STATUS_CHOICES]
        if new_status in valid_statuses:
            claim.status = new_status
            if status_reason:
                claim.status_reason = status_reason
            claim.save()
            messages.success(request, f'Claim {claim.claim_number} status updated to "{new_status}".')
        else:
            messages.error(request, 'Invalid status value.')
    return redirect(reverse("warranty_admin_list") + "?tab=claims")

# --- Warranty Registration Edit (Admin/Accountant) ----------------------------
@require_permission('INVENTORY', 'write')
def warranty_admin_edit_registration(request, reg_id):
    """Internal: edit invoice date (and other fields) of a WarrantyRegistration."""
    from .models import WarrantyRegistration
    reg = get_object_or_404(WarrantyRegistration, id=reg_id)

    if request.method == 'POST':
        reg.save()
        messages.success(request, f'Warranty registration #{reg.registration_number} updated successfully.')
        return redirect(reverse("warranty_admin_list") + "?tab=registrations")

    return render(request, 'inventory/warranty_admin_edit_registration.html', {'reg': reg})


@require_permission('INVENTORY', 'read')
def get_product_linked_bills_api(request, product_id):
    """Returns linked commercial bills/documents for an inventory product."""
    product = get_object_or_404(Product, id=product_id)
    from documents.models import DocumentItem
    doc_items = DocumentItem.objects.filter(product=product).select_related('document', 'document__contact').order_by('-document__date')
    
    linked_bills = []
    for item in doc_items:
        doc = item.document
        is_addition = doc.type in ['PO', 'CRN']
        linked_bills.append({
            'doc_id': doc.id,
            'number': doc.number,
            'type': doc.type,
            'type_display': doc.get_type_display(),
            'contact_name': doc.contact.name if doc.contact else 'N/A',
            'date': doc.date.strftime('%d %b %Y') if doc.date else '',
            'quantity': float(item.quantity),
            'is_addition': is_addition,
            'status': doc.status,
            'url': f"/documents/{doc.id}/preview/"
        })
        
    return JsonResponse({
        'success': True,
        'product_name': product.name,
        'sku': product.sku,
        'current_stock': float(product.current_stock),
        'unit': product.unit,
        'bills': linked_bills
    })

import csv
from django.http import HttpResponse

@require_permission('INVENTORY', 'read')
def inventory_export_csv(request):
    """Export inventory list to CSV."""
    # Apply same filters as inventory_list
    category = request.GET.get('category', 'All')
    q = request.GET.get('q', '').strip()
    
    products = Product.objects.all().order_by('name')
    if category != 'All':
        products = products.filter(category=category)
    if q:
        products = products.filter(
            Q(name__icontains=q) | 
            Q(sku__icontains=q) | 
            Q(category__icontains=q)
        )
        
    products = products.annotate(
        total_in=Coalesce(Sum('stock_transactions__quantity', filter=Q(stock_transactions__transaction_type='IN')), Value(0, output_field=DecimalField())),
        total_out=Coalesce(Sum('stock_transactions__quantity', filter=Q(stock_transactions__transaction_type='OUT')), Value(0, output_field=DecimalField()))
    )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="inventory_export.csv"'

    writer = csv.writer(response)
    writer.writerow(['SKU', 'Name', 'Category', 'Brand', 'HSN Code', 'Unit', 'Purchase Price', 'Selling Price', 'Tax Rate (%)', 'Stock (IN)', 'Stock (OUT)', 'Net Stock', 'Reorder Level', 'Status'])

    for p in products:
        net_stock = (p.total_in or 0) - (p.total_out or 0)
        if net_stock <= 0:
            status = 'Out of Stock'
        elif p.reorder_level and net_stock <= p.reorder_level:
            status = 'Low Stock'
        else:
            status = 'In Stock'
        writer.writerow([
            p.sku,
            p.name,
            p.category or '',
            p.brand or '',
            p.hsn_code or '',
            p.unit,
            p.purchase_price,
            p.selling_price,
            p.tax_rate,
            p.total_in,
            p.total_out,
            net_stock,
            p.reorder_level,
            status,
        ])

    return response
