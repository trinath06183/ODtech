from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from django.db.models import Q
from core.decorators import login_required, role_required
from .models import Product, StockTransaction


# ─── Product List ─────────────────────────────────────────────────────────────
@login_required
def inventory_list(request):
    query = request.GET.get('q', '').strip()
    products = Product.objects.all().order_by('name')
    
    if query:
        products = products.filter(
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

    low_stock_count = sum(1 for p in Product.objects.all() if p.is_low_stock)

    return render(request, 'inventory/inventory_list.html', {
        'products': products,
        'query': query,
        'suggestions': suggestions[:15],
        'low_stock_count': low_stock_count,
    })


# ─── Product Create (Admin only) ──────────────────────────────────────────────
@role_required('Admin')
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
@role_required('Admin')
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

    next_url = request.POST.get('next') or request.GET.get('next', '').strip()
    return render(request, 'inventory/product_form.html', {
        'form_title':   f'Edit Product — {product.name}',
        'submit_label': 'Save Changes',
        'product':      product,
        'next_url':     next_url,
    })


# ─── Product Delete (Admin only) ──────────────────────────────────────────────
@role_required('Admin')
def product_delete(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    if request.method == 'POST':
        # Safety check: block deletion if product is referenced
        has_stock_txns = StockTransaction.objects.filter(product=product).exists()
        has_doc_items  = product.documentitem_set.exists()

        if has_stock_txns or has_doc_items:
            messages.error(
                request,
                f'Cannot delete "{product.name}" — it is referenced by existing '
                f'{"stock transactions" if has_stock_txns else ""}'
                f'{" and " if has_stock_txns and has_doc_items else ""}'
                f'{"document line items" if has_doc_items else ""}. '
                'Remove those references first.'
            )
            return redirect('inventory_list')

        name = product.name
        product.delete()
        messages.success(request, f'Product "{name}" deleted successfully.')
        return redirect('inventory_list')

    # GET: confirmation page
    return render(request, 'inventory/product_confirm_delete.html', {'product': product})


# ─── Stock Adjustment (Admin only) ────────────────────────────────────────────
@role_required('Admin')
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
@login_required
def warranty_tracker(request):
    from documents.models import DocumentItem
    from datetime import date
    from dateutil.relativedelta import relativedelta

    query = request.GET.get('q', '').strip()
    results = []

    if query:
        items = DocumentItem.objects.select_related('document', 'product', 'document__contact').filter(
            Q(serial_number__icontains=query) |
            Q(document__number__icontains=query) |
            Q(document__contact__name__icontains=query) |
            Q(product__sku__icontains=query) |
            Q(product__name__icontains=query)
        ).filter(
            document__type__in=['INV', 'CHL'],
            document__status='Approved'
        ).distinct().order_by('-document__date')

        for item in items:
            warranty_months = item.product.warranty_months
            expiry_date = item.document.date + relativedelta(months=warranty_months)
            is_active = date.today() <= expiry_date
            
            results.append({
                'item': item,
                'document': item.document,
                'product': item.product,
                'customer_name': item.document.contact.name if item.document.contact else 'N/A',
                'invoice_date': item.document.date,
                'expiry_date': expiry_date,
                'is_active': is_active,
                'warranty_months': warranty_months
            })

    return render(request, 'inventory/warranty_tracker.html', {
        'query': query,
        'results': results
    })


# ------------------------------------------------------------------------------
# WARRANTY PORTAL VIEWS
# ------------------------------------------------------------------------------

# --- Warranty Registration ----------------------------------------------------
def warranty_register(request):
    """Public: display and process the warranty registration form."""
    from .models import WarrantyRegistration

    if request.method == 'POST':
        invoice_number   = request.POST.get('invoice_number', '').strip()
        serial_number    = request.POST.get('serial_number', '').strip()
        invoice_date     = request.POST.get('invoice_date', '').strip()
        invoice_amount   = request.POST.get('invoice_amount', '').strip()
        company_name     = request.POST.get('company_name', '').strip()
        gst_number       = request.POST.get('gst_number', '').strip() or None
        email            = request.POST.get('email', '').strip()
        contact_number   = request.POST.get('contact_number', '').strip()
        product_image    = request.FILES.get('product_image')
        invoice_document = request.FILES.get('invoice_document')

        errors = []
        if not invoice_number:   errors.append('Invoice number is required.')
        if not serial_number:    errors.append('Serial number is required.')
        if not invoice_date:     errors.append('Invoice date is required.')
        if not invoice_amount:   errors.append('Invoice amount is required.')
        if not company_name:     errors.append('Company / Customer name is required.')
        if not email:            errors.append('Email address is required.')
        if not contact_number:   errors.append('Contact number is required.')
        if not product_image:    errors.append('Product image is required.')
        if not invoice_document: errors.append('Invoice document is required.')

        if not errors:
            try:
                from decimal import Decimal, InvalidOperation
                amount = Decimal(invoice_amount)
            except (InvalidOperation, ValueError):
                errors.append('Invoice amount must be a valid number.')

        if errors:
            return render(request, 'inventory/warranty_register.html', {
                'errors': errors,
                'post': request.POST,
            })

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

    return render(request, 'inventory/warranty_register.html', {})


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
@role_required('Admin', 'Accountant')
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


@role_required('Admin', 'Accountant')
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
@role_required('Admin', 'Accountant')
def warranty_admin_edit_registration(request, reg_id):
    """Internal: edit invoice date (and other fields) of a WarrantyRegistration."""
    from .models import WarrantyRegistration
    reg = get_object_or_404(WarrantyRegistration, id=reg_id)

    if request.method == 'POST':
        pass

    return render(request, 'inventory/warranty_admin_edit_registration.html', {'reg': reg})
