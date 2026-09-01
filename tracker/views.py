from core.decorators import require_permission
import csv
import io
import os
import re
import shutil
import zipfile
from datetime import datetime
from django.db.models import Prefetch, Q, Sum, F, ExpressionWrapper, DecimalField
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy, reverse
from django.http import HttpResponse, JsonResponse, FileResponse
from django.contrib import messages
from .models import Order, Lot, Product, SupplierCostOption, ProductBookmark, Notification, InternalNote, AuditLog, PriceApprovalRequest, Task, OrderExpense
from .forms import OrderForm, LotForm, ProductForm, SupplierCostOptionForm, CSVUploadForm, ProductPricingForm
from django.views.decorators.http import require_POST
import json

def _sync_selected_supplier_from_product(product, user):
    selected = product.selected_supplier
    if selected:
        selected.base_price = product.buying_price_ex_gst
        selected.total_inc_gst = product.buying_price_inc_gst
        selected.gst_percentage = product.gst_percentage
        selected.updated_by = user
        selected.save()

def _apply_qr_upload(request, supplier_option):
    """
    If the form contained a qr_upload_token and no direct file was uploaded,
    fetch the file from the MobileUploadSession and attach it to the supplier option.
    """
    token = request.POST.get('qr_upload_token', '').strip()
    # Only apply if no direct file was uploaded for photo_or_document
    if token and not request.FILES.get('photo_or_document'):
        try:
            from mobile_upload.models import MobileUploadSession
            session = MobileUploadSession.objects.get(
                token=token,
                created_by=request.user,
                status=MobileUploadSession.STATUS_COMPLETED
            )
            if session.uploaded_file:
                supplier_option.photo_or_document = session.uploaded_file
                supplier_option.save(update_fields=['photo_or_document'])
        except Exception:
            pass  # Silently skip if session not found or already used

# --- Shared helper for product list context (eliminates duplication) ---
def _build_product_list_context(request, products_qs, order, lot=None):
    """Build context for product_list.html with optimized queries."""
    # Prefetch supplier_options to avoid N+1 queries
    products = list(
        products_qs
        .select_related('lot')
        .prefetch_related(
            Prefetch(
                'supplier_options',
                queryset=SupplierCostOption.objects.filter(is_selected=True),
                to_attr='_selected_suppliers'
            ),
            Prefetch(
                'price_approval_requests',
                queryset=PriceApprovalRequest.objects.filter(status='PENDING'),
                to_attr='_pending_requests'
            )
        )
        .order_by('lot__created_at', 'sl_no')
    )

    # Batch-fetch bookmarks for the current user
    product_ids = [p.id for p in products]
    bookmarks = ProductBookmark.objects.filter(user=request.user, product_id__in=product_ids)
    bookmark_dict = {b.product_id: b for b in bookmarks}
    bookmarked_ids = set(bookmark_dict.keys())

    # Annotate each product with cached supplier + bookmark (no extra queries)
    brands = set()
    suppliers = set()
    locations = set()
    for p in products:
        p.user_bookmark = bookmark_dict.get(p.id)
        # Use prefetched selected supplier instead of a per-product query
        p.cached_selected_supplier = p._selected_suppliers[0] if p._selected_suppliers else None
        p.pending_price_request = p._pending_requests[0] if hasattr(p, '_pending_requests') and p._pending_requests else None

        if p.make_or_model:
            for b in re.split(r'[,/;]', p.make_or_model):
                b_clean = b.strip()
                if b_clean:
                    brands.add(b_clean)

        if p.cached_selected_supplier and p.cached_selected_supplier.supplier_name:
            suppliers.add(p.cached_selected_supplier.supplier_name.strip())

    # Collect locations from all supplier options for this order
    from django.db.models import Q as _Q
    locations = sorted(set(
        v for v in SupplierCostOption.objects
            .filter(product__order=order)
            .exclude(location='')
            .exclude(location__isnull=True)
            .values_list('location', flat=True)
            .distinct()
    ))
    
    # Fetch Order Expenses
    from .models import OrderExpense, ProductExpense
    order_expenses = OrderExpense.objects.filter(order=order)
    order_expenses_ex_gst = sum(e.amount_ex_gst for e in order_expenses)
    order_expenses_inc_gst = sum(e.amount_inc_gst for e in order_expenses)

    # Fetch Product Expenses
    product_expenses = list(ProductExpense.objects.filter(product__order=order).select_related('product'))
    product_expenses_total = 0
    for e in product_expenses:
        if e.expense_type == 'PER_UNIT':
            e.total_amount = e.amount * e.product.quantity
        else:
            e.total_amount = e.amount
        product_expenses_total += e.total_amount

    # Fetch Linked Expenses from Payments
    linked_expenses = []
    try:
        from payments.models import Expense
        import json
        approved_expenses = Expense.objects.filter(status='Approved')
        for le in approved_expenses:
            p_payload = le.payload or {}
            if isinstance(p_payload, str):
                try:
                    p_payload = json.loads(p_payload)
                except Exception:
                    p_payload = {}
            prod_id = p_payload.get('product_id')
            if prod_id:
                p_name = None
                for p in products:
                    if str(p.id) == prod_id:
                        p_name = p.item_name
                        break
                if p_name:
                    linked_expenses.append({
                        'product_name': p_name,
                        'description': f"{le.expense_type or le.title} (Linked Payment Expense)",
                        'type': 'TOTAL',
                        'amount': le.amount,
                    })
                    product_expenses_total += le.amount
    except Exception as e:
        pass

    return {
        'order': order,
        'products': products,
        'lot': lot,
        'bookmarked_ids': bookmarked_ids,
        'brands': sorted(brands),
        'suppliers': sorted(suppliers),
        'locations': locations,
        'order_expenses': order_expenses,
        'order_expenses_ex_gst': order_expenses_ex_gst,
        'order_expenses_inc_gst': order_expenses_inc_gst,
        'product_expenses': product_expenses,
        'linked_expenses': linked_expenses,
        'product_expenses_total': product_expenses_total,
    }


# --- Original Function Based Views for Reading ---
@require_permission('TRACKER', 'read')
def dashboard_view(request):
    base_qs = Order.objects.select_related('created_by', 'updated_by').prefetch_related('products', 'tasks').order_by('-order_date')
    # Completed: CLOSED status + PAID payment — shown in a separate archived section
    completed_orders = base_qs.filter(order_status='CLOSED', payment_status='PAID')
    active_orders    = base_qs.exclude(order_status='CLOSED', payment_status='PAID')
    status_choices   = Order.STATUS_CHOICES

    # Build supplier → order mapping for client-side supplier filter
    # Returns: { 'Supplier Name': ['order-uuid-1', 'order-uuid-2', ...], ... }
    from collections import defaultdict
    supplier_rows = (
        SupplierCostOption.objects
        .filter(is_selected=True, product__order__isnull=False)
        .exclude(supplier_name='')
        .values('supplier_name', 'product__order_id')
        .distinct()
    )
    supplier_order_map = defaultdict(list)
    for row in supplier_rows:
        supplier_order_map[row['supplier_name']].append(str(row['product__order_id']))
    supplier_order_map = dict(supplier_order_map)  # plain dict for JSON serialization

    # Distinct customer names for the customer filter
    all_customers = sorted(
        Order.objects.exclude(customer_name='')
        .values_list('customer_name', flat=True)
        .distinct()
    )

    return render(request, 'tracker/dashboard.html', {
        'orders':             active_orders,
        'completed_orders':   completed_orders,
        'status_choices':     status_choices,
        'supplier_order_map': supplier_order_map,
        'all_customers':      all_customers,
    })


@require_permission('TRACKER', 'read')
def individual_products_view(request):
    """
    Flattened view of ALL products across all orders.
    Each product tracks its own Customer-side and Supplier-side stage independently.
    Supports filtering by: customer_stage, supplier_stage, order status, text search.
    """
    # Base queryset — eager-load related objects to avoid N+1
    products_qs = (
        Product.objects
        .select_related('order', 'lot', 'order__created_by', 'order__updated_by')
        .prefetch_related('supplier_options')
        .order_by('-order__order_date', 'sl_no')
    )

    # ---------- Filters from GET params ----------
    customer_stage_filter = request.GET.get('customer_stage', '').strip()
    supplier_stage_filter = request.GET.get('supplier_stage', '').strip()
    order_status_filter   = request.GET.get('order_status', '').strip()
    search_query          = request.GET.get('q', '').strip()
    start_date            = request.GET.get('start_date', '').strip()
    end_date              = request.GET.get('end_date', '').strip()

    if customer_stage_filter:
        products_qs = products_qs.filter(customer_stage=customer_stage_filter)
    if supplier_stage_filter:
        products_qs = products_qs.filter(supplier_stage=supplier_stage_filter)
    if order_status_filter:
        products_qs = products_qs.filter(order__order_status=order_status_filter)
    if search_query:
        products_qs = products_qs.filter(
            Q(item_name__icontains=search_query) |
            Q(order__customer_name__icontains=search_query) |
            Q(order__order_number__icontains=search_query) |
            Q(description__icontains=search_query)
        )
    if start_date:
        products_qs = products_qs.filter(order__created_at__gte=start_date)
    if end_date:
        # Include the entire end date by adding 1 day, or assuming order__created_at is datetime
        from django.utils import timezone
        import datetime
        try:
            end_dt = datetime.datetime.strptime(end_date, '%Y-%m-%d').date() + datetime.timedelta(days=1)
            products_qs = products_qs.filter(order__created_at__lt=end_dt)
        except ValueError:
            products_qs = products_qs.filter(order__created_at__lte=end_date)

    total_count    = products_qs.count()
    filtered_count = total_count  # same since filtering is already applied

    return render(request, 'tracker/individual_products.html', {
        'products':               products_qs,
        'total_count':            total_count,
        'customer_stage_choices': Product.CUSTOMER_STAGE_CHOICES,
        'supplier_stage_choices': Product.SUPPLIER_STAGE_CHOICES,
        'order_status_choices':   Order.STATUS_CHOICES,
        # Active filter values (to pre-select dropdowns)
        'f_customer_stage':  customer_stage_filter,
        'f_supplier_stage':  supplier_stage_filter,
        'f_order_status':    order_status_filter,
        'f_search':          search_query,
    })

@require_permission('TRACKER', 'read')
def order_detail_view(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    context = _build_product_list_context(request, order.products.all(), order)
    return render(request, 'tracker/product_list.html', context)

@require_permission('TRACKER', 'read')
def lot_detail_view(request, lot_id):
    lot = get_object_or_404(Lot.objects.select_related('order'), id=lot_id)
    context = _build_product_list_context(request, lot.products.all(), lot.order, lot=lot)
    return render(request, 'tracker/product_list.html', context)


@require_permission('TRACKER', 'read')
def product_detail_view(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    supplier_options = product.supplier_options.all()
    
    create_form = SupplierCostOptionForm()
    update_form = None
    update_option_id = None
    show_create = False

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_supplier':
            form = SupplierCostOptionForm(request.POST, request.FILES)
            if form.is_valid():
                supplier = form.save(commit=False)
                supplier.product = product
                supplier.created_by = request.user
                supplier.updated_by = request.user
                supplier.save()
                
                # Attach QR-uploaded file if any
                _apply_qr_upload(request, supplier)
                
                if supplier.is_selected:
                    product.supplier_options.exclude(id=supplier.id).update(is_selected=False)
                    product.buying_price_ex_gst = supplier.base_price
                    product.buying_price_inc_gst = supplier.total_inc_gst
                    product.gst_percentage = supplier.gst_percentage
                    product.save()
                return JsonResponse({'success': True})
            else:
                errors = {field: error_list[0] for field, error_list in form.errors.items()}
                return JsonResponse({'success': False, 'errors': errors})

        elif action == 'edit_supplier':
            option_id = request.POST.get('option_id')
            option = get_object_or_404(SupplierCostOption, id=option_id, product=product)
            form = SupplierCostOptionForm(request.POST, request.FILES, instance=option)
            if form.is_valid():
                supplier = form.save(commit=False)
                supplier.updated_by = request.user
                supplier.save()
                
                # Attach QR-uploaded file if any
                _apply_qr_upload(request, supplier)
                
                if supplier.is_selected:
                    product.supplier_options.exclude(id=supplier.id).update(is_selected=False)
                    product.buying_price_ex_gst = supplier.base_price
                    product.buying_price_inc_gst = supplier.total_inc_gst
                    product.gst_percentage = supplier.gst_percentage
                    product.save()
                return JsonResponse({'success': True})
            else:
                errors = {field: error_list[0] for field, error_list in form.errors.items()}
                return JsonResponse({'success': False, 'errors': errors})
            
        elif action == 'select_supplier':
            option_id = request.POST.get('option_id')
            option = get_object_or_404(SupplierCostOption, id=option_id, product=product)
            
            # Deselect all others and select this one, sync product price
            product.supplier_options.exclude(id=option.id).update(is_selected=False)
            option.is_selected = True
            option.updated_by = request.user
            option.save()
            product.buying_price_ex_gst = option.base_price
            product.buying_price_inc_gst = option.total_inc_gst
            product.gst_percentage = option.gst_percentage
            product.save()
            messages.success(request, f'{option.supplier_name} marked as the selected supplier.')
            return redirect(reverse('tracker:product_detail', kwargs={'product_id': product.id}))
            
        elif action == 'update_product_pricing':
            has_perm = request.user.is_staff
            if not has_perm and hasattr(request.user, 'field_visibility'):
                fv = request.user.field_visibility
                if fv.can_see_purchase_price or fv.can_see_selling_price:
                    has_perm = True
            
            if not has_perm:
                return JsonResponse({'success': False, 'error': 'You do not have permission to modify pricing.'}, status=403)
                
            pricing_form = ProductPricingForm(request.POST, instance=product)
            if pricing_form.is_valid():
                cd = pricing_form.cleaned_data

                res = _process_price_update(
                    request, product,
                    cd.get('buying_price_ex_gst'),
                    cd.get('buying_price_inc_gst'),
                    cd.get('selling_price_ex_gst'),
                    cd.get('selling_price_inc_gst'),
                    cd.get('gst_percentage')
                )
                
                _sync_selected_supplier_from_product(product, request.user)
                
                # Handle expenses
                expense_ids = request.POST.getlist('expense_id[]')
                expense_descs = request.POST.getlist('expense_desc[]')
                expense_amounts = request.POST.getlist('expense_amount[]')
                expense_types = request.POST.getlist('expense_type[]')
                
                existing_expense_ids = set()
                from .models import ProductExpense
                for exp_id, desc, amount, exp_type in zip(expense_ids, expense_descs, expense_amounts, expense_types):
                    if not desc.strip() or not amount.strip():
                        continue
                    if exp_id: # Update
                        try:
                            exp = ProductExpense.objects.get(id=exp_id, product=product)
                            exp.description = desc
                            exp.amount = amount
                            exp.expense_type = exp_type
                            exp.save()
                            existing_expense_ids.add(exp.id)
                        except ProductExpense.DoesNotExist:
                            pass
                    else: # Create
                        exp = ProductExpense.objects.create(product=product, description=desc, amount=amount, expense_type=exp_type)
                        existing_expense_ids.add(exp.id)
                
                product.expenses.exclude(id__in=existing_expense_ids).delete()
                
                if res['requires_approval']:
                    messages.warning(request, 'Product pricing submitted for admin approval.')
                else:
                    messages.success(request, 'Product pricing updated successfully.')
                return redirect(reverse('tracker:product_detail', kwargs={'product_id': product.id}))
            else:
                messages.error(request, 'Error updating product pricing.')

    pricing_form = ProductPricingForm(instance=product)
    
    options_with_forms = []
    for option in supplier_options:
        if update_option_id == option.id and update_form:
            options_with_forms.append({'option': option, 'form': update_form})
        else:
            options_with_forms.append({'option': option, 'form': SupplierCostOptionForm(instance=option)})

    # Fetch unique suppliers for autocomplete (optimized: only fetch needed fields)
    import json
    all_suppliers = (
        SupplierCostOption.objects
        .exclude(supplier_name='')
        .values('supplier_name', 'contact_email', 'contact_number', 'location')
        .order_by('-updated_at')
        .order_by('-updated_at')
    )
    supplier_dict = {}
    for s in all_suppliers:
        name = s['supplier_name'].strip()
        if name not in supplier_dict:
            supplier_dict[name] = {
                'name': name,
                'email': s['contact_email'] or '',
                'phone': s['contact_number'] or '',
                'location': s['location'] or ''
            }
    unique_suppliers = list(supplier_dict.values())
    unique_suppliers_json = json.dumps(unique_suppliers)

    # Fetch expenses
    expenses = product.expenses.all()
    expenses_list = [{'id': str(e.id), 'desc': e.description, 'amount': str(e.amount), 'type': getattr(e, 'expense_type', 'PER_UNIT'), 'is_linked': False} for e in expenses]

    # Fetch linked payments.Expense items
    try:
        from payments.models import Expense
        approved_expenses = Expense.objects.filter(status='Approved')
        for le in approved_expenses:
            p_payload = le.payload or {}
            if isinstance(p_payload, str):
                import json
                try:
                    p_payload = json.loads(p_payload)
                except Exception:
                    p_payload = {}
            if p_payload.get('product_id') == str(product.id):
                expenses_list.append({
                    'id': f'linked_{le.id}', 
                    'desc': f"{le.title} (Linked Expense)", 
                    'amount': str(le.amount), 
                    'type': 'TOTAL',
                    'is_linked': True
                })
    except Exception:
        pass

    product_expenses_json = json.dumps(expenses_list)

    pending_request = product.price_approval_requests.filter(status='PENDING').first()

    context = {
        'product': product,
        'supplier_options': supplier_options,
        'options_with_forms': options_with_forms,
        'create_form': create_form,
        'pricing_form': pricing_form,
        'selected_supplier': product.selected_supplier,
        'update_option_id': update_option_id,
        'show_create': show_create,
        'unique_suppliers_json': unique_suppliers_json,
        'unique_suppliers': unique_suppliers,
        'product_expenses_json': product_expenses_json,
        'pending_request': pending_request,
    }
    return render(request, 'tracker/product_detail.html', context)

@require_permission('TRACKER', 'read')
def product_modal_detail_view(request, product_id):
    product = get_object_or_404(Product.objects.select_related('lot').prefetch_related('supplier_options', 'expenses'), id=product_id)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'save_product':
            pricing_form = ProductPricingForm(request.POST, instance=product)
            if pricing_form.is_valid():
                cd = pricing_form.cleaned_data

                res = _process_price_update(
                    request, product,
                    cd.get('buying_price_ex_gst'),
                    cd.get('buying_price_inc_gst'),
                    cd.get('selling_price_ex_gst'),
                    cd.get('selling_price_inc_gst'),
                    cd.get('gst_percentage')
                )
                
                _sync_selected_supplier_from_product(product, request.user)
                
                # Handle expenses
                expense_ids = request.POST.getlist('expense_id[]')
                expense_descs = request.POST.getlist('expense_desc[]')
                expense_amounts = request.POST.getlist('expense_amount[]')
                expense_types = request.POST.getlist('expense_type[]')
                
                existing_expense_ids = set()
                from .models import ProductExpense
                for exp_id, desc, amount, exp_type in zip(expense_ids, expense_descs, expense_amounts, expense_types):
                    if not desc.strip() or not amount.strip():
                        continue
                    if exp_id: # Update
                        try:
                            exp = ProductExpense.objects.get(id=exp_id, product=product)
                            exp.description = desc
                            exp.amount = amount
                            exp.expense_type = exp_type
                            exp.save()
                            existing_expense_ids.add(exp.id)
                        except ProductExpense.DoesNotExist:
                            pass
                    else: # Create
                        exp = ProductExpense.objects.create(product=product, description=desc, amount=amount, expense_type=exp_type)
                        existing_expense_ids.add(exp.id)
                
                product.expenses.exclude(id__in=existing_expense_ids).delete()
                    
                if res['requires_approval']:
                    msg = f'Price update for "{product.item_name}" requires admin approval and has been submitted.'
                else:
                    msg = f'Pricing for "{product.item_name}" saved successfully.'
                messages.success(request, msg)
                return JsonResponse({'success': True, 'message': msg})
            else:
                errors = {}
                for field, error_list in pricing_form.errors.items():
                    errors[field] = error_list[0]
                return JsonResponse({'success': False, 'errors': errors})

        elif action == 'update_product_details':
            form = ProductForm(request.POST, request.FILES, instance=product)
            if form.is_valid():
                form.save()
                messages.success(request, f'Details for "{product.item_name}" updated successfully.')
                return JsonResponse({'success': True})
            else:
                errors = {field: error_list[0] for field, error_list in form.errors.items()}
                return JsonResponse({'success': False, 'errors': errors})
                
        elif action == 'select_supplier':
            option_id = request.POST.get('option_id')
            option = get_object_or_404(SupplierCostOption, id=option_id, product=product)
            product.supplier_options.exclude(id=option.id).update(is_selected=False)
            option.is_selected = True
            option.updated_by = request.user
            option.save()
            
            # Sync product buying price
            product.buying_price_ex_gst = option.base_price
            product.buying_price_inc_gst = option.total_inc_gst
            product.gst_percentage = option.gst_percentage
            product.save()
            return JsonResponse({'success': True})
            
        elif action == 'create_supplier':
            form = SupplierCostOptionForm(request.POST, request.FILES)
            if form.is_valid():
                supplier = form.save(commit=False)
                supplier.product = product
                supplier.created_by = request.user
                supplier.updated_by = request.user
                supplier.save()
                
                # Attach QR-uploaded file if any
                _apply_qr_upload(request, supplier)
                
                if supplier.is_selected:
                    product.supplier_options.exclude(id=supplier.id).update(is_selected=False)
                    product.buying_price_ex_gst = supplier.base_price
                    product.buying_price_inc_gst = supplier.total_inc_gst
                    product.gst_percentage = supplier.gst_percentage
                    product.save()
                return JsonResponse({'success': True})
            else:
                errors = {field: error_list[0] for field, error_list in form.errors.items()}
                return JsonResponse({'success': False, 'errors': errors})

        elif action == 'edit_supplier':
            option_id = request.POST.get('option_id')
            option = get_object_or_404(SupplierCostOption, id=option_id, product=product)
            form = SupplierCostOptionForm(request.POST, request.FILES, instance=option)
            if form.is_valid():
                supplier = form.save(commit=False)
                supplier.updated_by = request.user
                supplier.save()
                
                # Attach QR-uploaded file if any
                _apply_qr_upload(request, supplier)
                
                if supplier.is_selected:
                    product.supplier_options.exclude(id=supplier.id).update(is_selected=False)
                    product.buying_price_ex_gst = supplier.base_price
                    product.buying_price_inc_gst = supplier.total_inc_gst
                    product.gst_percentage = supplier.gst_percentage
                    product.save()
                return JsonResponse({'success': True})
            else:
                errors = {field: error_list[0] for field, error_list in form.errors.items()}
                return JsonResponse({'success': False, 'errors': errors})
                
        elif action == 'delete_supplier':
            option_id = request.POST.get('option_id')
            option = get_object_or_404(SupplierCostOption, id=option_id, product=product)
            was_selected = option.is_selected
            option.delete()
            if was_selected:
                # Clear pricing
                product.buying_price_ex_gst = 0
                product.buying_price_inc_gst = 0
                product.save()
            return JsonResponse({'success': True})

        elif action == 'delete_supplier_attachment':
            option_id = request.POST.get('option_id')
            option = get_object_or_404(SupplierCostOption, id=option_id, product=product)
            if option.photo_or_document:
                option.photo_or_document.delete(save=False)
                option.photo_or_document = None
                option.save(update_fields=['photo_or_document'])
            return JsonResponse({'success': True})
            
        return JsonResponse({'success': False, 'error': 'Invalid action'})
        
    # GET request
    product_form = ProductForm(instance=product)
    pricing_form = ProductPricingForm(instance=product)
    supplier_options = product.supplier_options.all()
    create_form = SupplierCostOptionForm()
    
    # Autofill supplier quotes suggestions list
    import json
    all_suppliers = (
        SupplierCostOption.objects
        .exclude(supplier_name='')
        .values('supplier_name', 'contact_email', 'contact_number', 'location')
        .order_by('-updated_at')
    )
    supplier_dict = {}
    for s in all_suppliers:
        name = s['supplier_name'].strip()
        if name not in supplier_dict:
            supplier_dict[name] = {
                'name': name,
                'email': s['contact_email'] or '',
                'phone': s['contact_number'] or '',
                'location': s['location'] or ''
            }
    unique_suppliers = list(supplier_dict.values())
    unique_suppliers_json = json.dumps(unique_suppliers)
    
    # Fetch expenses
    expenses = product.expenses.all()
    expenses_list = [{'id': str(e.id), 'desc': e.description, 'amount': str(e.amount), 'type': getattr(e, 'expense_type', 'PER_UNIT'), 'is_linked': False} for e in expenses]
    
    # Fetch linked payments.Expense items
    try:
        from payments.models import Expense
        approved_expenses = Expense.objects.filter(status='Approved')
        for le in approved_expenses:
            p_payload = le.payload or {}
            if isinstance(p_payload, str):
                import json
                try:
                    p_payload = json.loads(p_payload)
                except Exception:
                    p_payload = {}
            if p_payload.get('product_id') == str(product.id):
                expenses_list.append({
                    'id': f'linked_{le.id}', 
                    'desc': f"{le.title} (Linked Expense)", 
                    'amount': str(le.amount), 
                    'type': 'TOTAL',
                    'is_linked': True
                })
    except Exception:
        pass
        
    product_expenses_json = json.dumps(expenses_list)
    
    pending_request = product.price_approval_requests.filter(status='PENDING').first()
    
    context = {
        'product': product,
        'product_form': product_form,
        'pricing_form': pricing_form,
        'supplier_options': supplier_options,
        'selected_supplier': product.selected_supplier,
        'create_form': create_form,
        'unique_suppliers': unique_suppliers,
        'unique_suppliers_json': unique_suppliers_json,
        'product_expenses_json': product_expenses_json,
        'pending_request': pending_request,
    }
    return render(request, 'tracker/partials/product_detail_modal_content.html', context)


# --- CRUD Mixin ---
class BaseFormMixin(LoginRequiredMixin):
    template_name = 'tracker/form.html'

    def form_valid(self, form):
        if not hasattr(self, 'object') or not self.object:
            form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

# --- Order CRUD ---
class OrderCreateView(BaseFormMixin, CreateView):
    model = Order
    form_class = OrderForm
    success_url = reverse_lazy('tracker:dashboard')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Create Order'
        context['cancel_url'] = self.success_url
        return context

class OrderUpdateView(BaseFormMixin, UpdateView):
    model = Order
    form_class = OrderForm
    
    def get_success_url(self):
        return reverse('tracker:order_detail', kwargs={'order_id': self.object.id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Edit Order: {self.object.order_number}'
        context['cancel_url'] = self.get_success_url()
        return context

class OrderDeleteView(LoginRequiredMixin, DeleteView):
    model = Order
    template_name = 'tracker/confirm_delete.html'
    success_url = reverse_lazy('tracker:dashboard')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = self.success_url
        return context

# --- Lot CRUD ---
class LotCreateView(BaseFormMixin, CreateView):
    model = Lot
    form_class = LotForm

    def form_valid(self, form):
        order = get_object_or_404(Order, id=self.kwargs['order_id'])
        form.instance.order = order
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('tracker:order_detail', kwargs={'order_id': self.kwargs['order_id']})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add Lot'
        context['cancel_url'] = self.get_success_url()
        return context

class LotUpdateView(BaseFormMixin, UpdateView):
    model = Lot
    form_class = LotForm

    def get_success_url(self):
        return reverse('tracker:order_detail', kwargs={'order_id': self.object.order.id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Edit Lot: {self.object.lot_name}'
        context['cancel_url'] = self.get_success_url()
        return context

class LotDeleteView(LoginRequiredMixin, DeleteView):
    model = Lot
    template_name = 'tracker/lot_confirm_delete.html'

    def get_success_url(self):
        return reverse('tracker:order_detail', kwargs={'order_id': self.object.order.id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = self.get_success_url()
        context['products_count'] = self.object.products.count()
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.products.exists():
            delete_mode = request.POST.get('delete_mode')
            if delete_mode == 'all':
                self.object.products.all().delete()
        return super().post(request, *args, **kwargs)

# --- Product CRUD ---
class ProductCreateView(BaseFormMixin, CreateView):
    model = Product
    form_class = ProductForm

    def get_initial(self):
        initial = super().get_initial()
        if 'lot_id' in self.kwargs:
            initial['lot'] = self.kwargs['lot_id']
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if 'order_id' in self.kwargs:
            kwargs['order'] = get_object_or_404(Order, id=self.kwargs['order_id'])
        elif 'lot_id' in self.kwargs:
            lot = get_object_or_404(Lot, id=self.kwargs['lot_id'])
            kwargs['order'] = lot.order
        return kwargs

    def form_valid(self, form):
        if 'lot_id' in self.kwargs:
            # If created from a lot page, default to that lot (unless changed)
            if not form.cleaned_data.get('lot'):
                form.instance.lot = get_object_or_404(Lot, id=self.kwargs['lot_id'])
            form.instance.order = form.instance.lot.order
        else:
            order = get_object_or_404(Order, id=self.kwargs['order_id'])
            form.instance.order = order
            # Do not force lot to None here, let the form value pass through
        return super().form_valid(form)

    def get_success_url(self):
        if 'lot_id' in self.kwargs:
            return reverse('tracker:lot_detail', kwargs={'lot_id': self.kwargs['lot_id']})
        return reverse('tracker:order_detail', kwargs={'order_id': self.kwargs['order_id']})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = 'Add Product'
        context['cancel_url'] = self.get_success_url()
        return context

class ProductUpdateView(BaseFormMixin, UpdateView):
    model = Product
    form_class = ProductForm

    def get_success_url(self):
        return reverse('tracker:product_detail', kwargs={'product_id': self.object.id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f'Edit Product: {self.object.item_name}'
        context['cancel_url'] = self.get_success_url()
        return context

class ProductDeleteView(LoginRequiredMixin, DeleteView):
    model = Product
    template_name = 'tracker/confirm_delete.html'

    def get_success_url(self):
        if self.object.lot:
            return reverse('tracker:lot_detail', kwargs={'lot_id': self.object.lot.id})
        return reverse('tracker:order_detail', kwargs={'order_id': self.object.order.id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = self.get_success_url()
        return context

# --- Supplier Cost Option CRUD ---
class SupplierOptionDeleteView(LoginRequiredMixin, DeleteView):
    model = SupplierCostOption
    template_name = 'tracker/confirm_delete.html'

    def get_success_url(self):
        return reverse('tracker:product_detail', kwargs={'product_id': self.object.product.id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = self.get_success_url()
        return context


# --- CSV Bulk Product Upload ---
CSV_COLUMNS = ['sl_no', 'item_name', 'make_or_model', 'description', 'quantity', 'uom', 'status', 'Additional Remarks']

@require_permission('TRACKER', 'read')
def product_csv_upload_view(request, order_id=None, lot_id=None):
    """Upload multiple products from a CSV file into an order or lot."""
    if lot_id:
        lot = get_object_or_404(Lot, id=lot_id)
        order = lot.order
        success_url = reverse('tracker:lot_detail', kwargs={'lot_id': lot_id})
    else:
        lot = None
        order = get_object_or_404(Order, id=order_id)
        success_url = reverse('tracker:order_detail', kwargs={'order_id': order_id})

    form = CSVUploadForm(order=order, initial={'lot': lot})

    if request.method == 'POST':
        form = CSVUploadForm(request.POST, request.FILES, order=order)
        if form.is_valid():
            selected_lot = form.cleaned_data.get('lot')
            # If the user selected a lot in the form, use that instead of the URL's lot
            if selected_lot:
                lot = selected_lot
                
            csv_file = request.FILES['csv_file']
            if not csv_file.name.endswith('.csv'):
                messages.error(request, 'Please upload a valid .csv file.')
            else:
                try:
                    decoded = csv_file.read().decode('utf-8-sig')
                except UnicodeDecodeError:
                    csv_file.seek(0)
                    decoded = csv_file.read().decode('cp1252', errors='replace')
                reader = csv.DictReader(io.StringIO(decoded))
                created_count = 0

                for i, row in enumerate(reader, start=2):  # Row 1 is header
                    row = {k.strip(): v.strip() for k, v in row.items()}
                    try:
                        item_name = row.get('item_name', '').strip()
                        if not item_name:
                            messages.warning(request, f'Row {i}: item_name is required, skipped.')
                            continue

                        qty_raw = row.get('quantity', '1')
                        try:
                            qty = float(qty_raw) if qty_raw else 1
                        except ValueError:
                            qty = 1

                        status_raw = row.get('status', 'OPEN').upper().strip()
                        status = status_raw if status_raw in ['OPEN', 'CLOSED'] else 'OPEN'

                        Product.objects.create(
                            order=order,
                            lot=lot,
                            sl_no=row.get('sl_no', '').strip(),
                            item_name=item_name,
                            make_or_model=row.get('make_or_model', '').strip(),
                            description=row.get('description', '').strip(),
                            quantity=qty,
                            uom=row.get('uom', '').strip(),
                            status=status,
                            remark=row.get('Additional Remarks', row.get('remark', '')).strip(),
                            created_by=request.user,
                            updated_by=request.user,
                        )
                        created_count += 1
                    except Exception as e:
                        messages.warning(request, f'Row {i}: {str(e)}')

                if created_count:
                    messages.success(request, f'Successfully imported {created_count} product(s).')
                return redirect(success_url)

    context = {
        'form': form,
        'order': order,
        'lot': lot,
        'title': f'Bulk Upload Products — {lot.lot_name if lot else order.order_number}',
        'cancel_url': success_url,
        'csv_columns': CSV_COLUMNS,
    }
    return render(request, 'tracker/csv_upload.html', context)


@require_permission('TRACKER', 'write')
def download_sample_csv(request):
    """Serve a pre-filled sample CSV for users to use as a template."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="sample_products.csv"'
    writer = csv.writer(response)
    writer.writerow(['sl_no', 'item_name', 'make_or_model', 'description', 'quantity', 'uom', 'status', 'Additional Remarks'])
    writer.writerow(['1', 'Sample Item A', 'Model X', 'This is a sample description', '10', 'Pcs', 'OPEN', 'First priority'])
    writer.writerow(['2', 'Sample Item B', '', 'Another description here', '5', 'Sets', 'CLOSED', 'Checked externally'])
    writer.writerow(['3', 'Sample Item C', 'Brand Y', '', '100', 'Nos', 'OPEN', ''])
    writer.writerow(['', 'Sample Item D (No SL)', '', '', '2.5', 'Kgs', 'OPEN', ''])
    writer.writerow(['5', 'Sample Item E', '', 'Optional info', '20', 'Mtr', 'OPEN', ''])
    return response

@require_permission('TRACKER', 'write')
def bulk_move_products(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        target_lot_id = request.POST.get('target_lot_id')
        selected_products = request.POST.getlist('selected_products')

        if not selected_products:
            messages.warning(request, "No products selected.")
            return redirect('tracker:order_detail', order_id=order.id)
        
        products = Product.objects.filter(id__in=selected_products, order=order)
        
        if target_lot_id == 'unassigned':
            products.update(lot=None)
            messages.success(request, f"Successfully removed {products.count()} product(s) from their lots.")
        elif target_lot_id:
            try:
                target_lot = Lot.objects.get(id=target_lot_id, order=order)
                products.update(lot=target_lot)
                messages.success(request, f"Successfully moved {products.count()} product(s) to lot '{target_lot.lot_name}'.")
            except Lot.DoesNotExist:
                messages.error(request, "Target lot not found.")
        else:
            messages.error(request, "No target lot selected.")

    return redirect('tracker:order_detail', order_id=order.id)

@require_permission('TRACKER', 'write')
def bulk_delete_products(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        selected_products = request.POST.getlist('selected_products')

        if not selected_products:
            messages.warning(request, "No products selected.")
            return redirect('tracker:order_detail', order_id=order.id)
        
        products = Product.objects.filter(id__in=selected_products, order=order)
        count = products.count()
        if count > 0:
            products.delete()
            messages.success(request, f"Successfully deleted {count} product(s).")
        else:
            messages.warning(request, "Selected products not found.")

    return redirect('tracker:order_detail', order_id=order.id)


@require_permission('TRACKER', 'write')
def toggle_bookmark(request, product_id):
    """Toggle bookmark on a product. POST to add/update, DELETE to remove."""
    product = get_object_or_404(Product, id=product_id)

    if request.method == 'POST':
        action = request.POST.get('action', 'add')

        if action == 'remove':
            ProductBookmark.objects.filter(product=product, user=request.user).delete()
            messages.success(request, f'Bookmark removed from "{product.item_name}".')
        else:
            description = request.POST.get('description', '').strip()
            bookmark, created = ProductBookmark.objects.update_or_create(
                product=product,
                user=request.user,
                defaults={'description': description}
            )
            if created:
                messages.success(request, f'Bookmarked "{product.item_name}".')
            else:
                messages.success(request, f'Bookmark updated for "{product.item_name}".')

    # Redirect back to the referring page
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('tracker:order_detail', order_id=product.order.id)




@require_permission('TRACKER', 'read')
def toggle_purchase_view(request, product_id):
    """Toggle a product's purchased field."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST request required'}, status=405)
        
    product = get_object_or_404(Product, id=product_id)
    product.is_purchased = not product.is_purchased
    product.save()
    
    return JsonResponse({
        'success': True,
        'is_purchased': product.is_purchased,
    })

# ==============================================================================
# Master Search & Intelligence Views
# ==============================================================================

@require_permission('TRACKER', 'read')
def master_search_api(request):
    """AJAX endpoint for the Master Search feature."""
    query = request.GET.get('q', '').strip()
    if not query:
        return JsonResponse({'products': [], 'buyers': [], 'sellers': [], 'locations': []})

    # Search Products
    products_qs = Product.objects.filter(
        Q(item_name__icontains=query) |
        Q(make_or_model__icontains=query) |
        Q(description__icontains=query)
    ).values_list('item_name', flat=True).distinct()[:10]
    
    # Search Buyers (Orders)
    buyers_qs = Order.objects.filter(
        Q(customer_name__icontains=query) |
        Q(order_number__icontains=query)
    ).values_list('customer_name', flat=True).distinct()[:10]
    
    # Search Sellers (Suppliers)
    sellers_qs = SupplierCostOption.objects.filter(
        Q(supplier_name__icontains=query)
    ).values_list('supplier_name', flat=True).distinct()[:10]
    
    # Search Locations (from SupplierCostOption)
    locations_qs = SupplierCostOption.objects.filter(
        Q(location__icontains=query)
    ).values_list('location', flat=True).distinct()[:10]
    
    return JsonResponse({
        'products': list(products_qs),
        'buyers': list(buyers_qs),
        'sellers': list(sellers_qs),
        'locations': list(locations_qs),
    })

@require_permission('TRACKER', 'read')
def product_intelligence_view(request):
    """Aggregate product data across all orders."""
    product_name = request.GET.get('name', '')
    products = Product.objects.filter(item_name__iexact=product_name).select_related('order').order_by('-created_at')
    
    # Active Orders
    active_orders = []
    seen = set()
    for p in products:
        if p.order.id not in seen:
            seen.add(p.order.id)
            active_orders.append(p.order)
    
    # Available Sellers
    sellers = SupplierCostOption.objects.filter(product__in=products).select_related('product').order_by('-created_at')
    
    context = {
        'product_name': product_name,
        'products': products,
        'active_orders': active_orders,
        'sellers': sellers,
    }
    return render(request, 'tracker/intelligence/product_intelligence.html', context)

@require_permission('TRACKER', 'read')
def buyer_profile_view(request):
    """Aggregate order history for a specific customer."""
    buyer_name = request.GET.get('name', '')
    orders = Order.objects.filter(customer_name__iexact=buyer_name).prefetch_related('products').order_by('-order_date')
    
    total_value = sum(
        sum(p.selling_price_inc_gst * p.quantity for p in order.products.all())
        for order in orders
    )
    
    context = {
        'buyer_name': buyer_name,
        'orders': orders,
        'total_value': total_value,
    }
    return render(request, 'tracker/intelligence/buyer_profile.html', context)

@require_permission('TRACKER', 'read')
def seller_profile_view(request):
    """Aggregate supplier catalog and pricing across the platform."""
    seller_name = request.GET.get('name', '')
    supplier_options = SupplierCostOption.objects.filter(supplier_name__iexact=seller_name).select_related('product__order').order_by('-created_at')
    
    context = {
        'seller_name': seller_name,
        'supplier_options': supplier_options,
    }
    return render(request, 'tracker/intelligence/seller_profile.html', context)

@require_permission('TRACKER', 'read')
@require_POST
def update_order_status_api(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    try:
        data = json.loads(request.body)
        new_status = data.get('status')
        
        if new_status not in dict(Order.STATUS_CHOICES):
            return JsonResponse({'success': False, 'error': 'Invalid status.'}, status=400)
            
        # Validation Rule: PROCURED requires suppliers
        if new_status == 'PROCURED':
            products = order.products.all()
            for product in products:
                if not product.supplier_options.filter(is_selected=True).exists():
                    return JsonResponse({'success': False, 'error': f'Cannot move to PROCURED. Product "{product.item_name}" has no selected supplier.'}, status=400)
                    
        # Validation Rule: CLOSED requires PAID
        if new_status == 'CLOSED' and order.payment_status != 'PAID':
            return JsonResponse({'success': False, 'error': 'Cannot close an unpaid order.'}, status=400)
            
        order.order_status = new_status
        order.save()
        return JsonResponse({'success': True, 'status': order.order_status})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@require_permission('TRACKER', 'write')
@require_POST
def mark_notification_read_api(request, notification_id):
    notif = get_object_or_404(Notification, id=notification_id, user=request.user)
    notif.is_read = True
    notif.save()
    return JsonResponse({'success': True})

@require_permission('TRACKER', 'write')
@require_POST
def add_order_expense_api(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    try:
        data = json.loads(request.body)
        expense_name = data.get('expense_name', '').strip()
        amount_ex_gst = data.get('amount_ex_gst', 0)
        gst_percentage = data.get('gst_percentage', 18)
        amount_inc_gst = data.get('amount_inc_gst', 0)
        remark = data.get('remark', '').strip()
        
        if not expense_name:
            return JsonResponse({'success': False, 'error': 'Expense name is required'}, status=400)
            
        from .models import OrderExpense
        OrderExpense.objects.create(
            order=order,
            expense_name=expense_name,
            amount_ex_gst=amount_ex_gst,
            gst_percentage=gst_percentage,
            amount_inc_gst=amount_inc_gst,
            remark=remark,
            created_by=request.user
        )
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@require_permission('TRACKER', 'write')
@require_POST
def delete_order_expense_api(request, expense_id):
    from .models import OrderExpense
    expense = get_object_or_404(OrderExpense, id=expense_id)
    try:
        expense.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_permission('TRACKER', 'write')
@require_POST
def inline_update_product_api(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    try:
        data = json.loads(request.body)
        
        if 'sl_no' in data:
            product.sl_no = data['sl_no']
        if 'item_name' in data:
            product.item_name = data['item_name']
        if 'make_or_model' in data:
            product.make_or_model = data['make_or_model']
        if 'description' in data:
            product.description = data['description']
        if 'quantity' in data:
            try:
                product.quantity = float(data['quantity'])
            except ValueError:
                pass
        if 'uom' in data:
            product.uom = data['uom']
        if 'selling_price_ex_gst' in data:
            try:
                product.selling_price_ex_gst = float(data['selling_price_ex_gst'])
            except ValueError:
                pass
                
        product.updated_by = request.user
        product.save()
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@require_permission('TRACKER', 'read')
@require_POST
def bulk_update_product_status_api(request):
    try:
        data = json.loads(request.body)
        product_ids = data.get('product_ids', [])
        new_status = data.get('status')

        if not product_ids or not new_status:
            return JsonResponse({'success': False, 'error': 'Missing product IDs or status.'}, status=400)
            
        if new_status not in dict(Product.STATUS_CHOICES):
            return JsonResponse({'success': False, 'error': 'Invalid status.'}, status=400)
            
        updated_count = Product.objects.filter(id__in=product_ids).update(status=new_status)
        return JsonResponse({'success': True, 'updated_count': updated_count})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@require_permission('TRACKER', 'write')
@require_POST
def api_update_product_stage(request, product_id):
    """Update a product's Customer-side or Supplier-side stage independently.

    Request body:
        { "side": "customer" | "supplier", "stage": "STAGE_CODE" | "" }

    Passing an empty string for stage clears that side.
    """
    product = get_object_or_404(Product, id=product_id)
    try:
        data      = json.loads(request.body)
        side      = data.get('side', '').strip().lower()   # 'customer' or 'supplier'
        new_stage = data.get('stage', '').strip()

        if side not in ('customer', 'supplier'):
            return JsonResponse({'success': False, 'error': "Invalid side — must be 'customer' or 'supplier'."}, status=400)

        if side == 'customer':
            valid = dict(Product.CUSTOMER_STAGE_CHOICES)
            if new_stage and new_stage not in valid:
                return JsonResponse({'success': False, 'error': 'Invalid customer stage value.'}, status=400)
            product.customer_stage = new_stage if new_stage else None
            product.save(update_fields=['customer_stage', 'updated_by', 'updated_at'])
            label = valid.get(product.customer_stage, '')
            return JsonResponse({
                'success': True,
                'side': 'customer',
                'stage': product.customer_stage,
                'stage_label': label,
            })
        else:  # supplier
            valid = dict(Product.SUPPLIER_STAGE_CHOICES)
            if new_stage and new_stage not in valid:
                return JsonResponse({'success': False, 'error': 'Invalid supplier stage value.'}, status=400)
            product.supplier_stage = new_stage if new_stage else None
            product.save(update_fields=['supplier_stage', 'updated_by', 'updated_at'])
            label = valid.get(product.supplier_stage, '')
            return JsonResponse({
                'success': True,
                'side': 'supplier',
                'stage': product.supplier_stage,
                'stage_label': label,
            })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@require_permission('TRACKER', 'write')
@require_POST
def bulk_attribute_edit_api(request):
    """
    Batch-update one or more attributes on multiple products at once.

    Request body (JSON):
        {
            "product_ids": ["uuid1", "uuid2", ...],
            "patch": {
                "status":       "SOURCING",   // optional
                "remark":       "Some note",  // optional
                "uom":          "Sets",       // optional
                "is_purchased": true          // optional
            }
        }

    All patch fields are optional — at least one must be supplied.
    Returns:
        { "success": true, "updated_count": N, "patch": {...} }
    """
    # ── 1. Parse body ──────────────────────────────────────────────────────
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON body.'}, status=400)

    product_ids = data.get('product_ids', [])
    patch       = data.get('patch', {})

    # ── 2. Basic input validation ──────────────────────────────────────────
    if not product_ids:
        return JsonResponse({'success': False, 'error': 'No product IDs supplied.'}, status=400)

    if not patch:
        return JsonResponse({'success': False, 'error': 'No fields to update.'}, status=400)

    # ── 3. Whitelist allowed fields to prevent arbitrary column injection ──
    ALLOWED_FIELDS = {'status', 'remark', 'uom', 'is_purchased'}
    invalid_fields = set(patch.keys()) - ALLOWED_FIELDS
    if invalid_fields:
        return JsonResponse(
            {'success': False, 'error': f'Unsupported field(s): {", ".join(invalid_fields)}'},
            status=400
        )

    # ── 4. Per-field value validation ──────────────────────────────────────
    valid_statuses = {k for k, _ in Product.STATUS_CHOICES}
    valid_uoms     = {k for k, _ in Product.UOM_CHOICES}

    if 'status' in patch and patch['status'] not in valid_statuses:
        return JsonResponse({'success': False, 'error': f'Invalid status: {patch["status"]}'}, status=400)

    if 'uom' in patch and patch['uom'] not in valid_uoms:
        return JsonResponse({'success': False, 'error': f'Invalid UOM: {patch["uom"]}'}, status=400)

    if 'is_purchased' in patch:
        val = patch['is_purchased']
        if not isinstance(val, bool):
            return JsonResponse({'success': False, 'error': 'is_purchased must be a boolean.'}, status=400)

    # ── 5. Scope query to valid products ──────────────────────────────────
    products_qs = Product.objects.filter(id__in=product_ids)
    if not products_qs.exists():
        return JsonResponse({'success': False, 'error': 'No matching products found.'}, status=404)

    # ── 6. Snapshot old values for audit logging ───────────────────────────
    audit_fields = list(patch.keys())
    snapshots = list(products_qs.values('id', *audit_fields))

    # ── 7. Perform the batch update ────────────────────────────────────────
    try:
        update_payload = dict(patch)
        update_payload['updated_by'] = request.user
        updated_count = products_qs.update(**update_payload)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Database error: {str(e)}'}, status=500)

    # ── 8. Write audit log entries ─────────────────────────────────────────
    audit_entries = []
    for row in snapshots:
        changes = {}
        for field in audit_fields:
            changes[field] = {'old': str(row.get(field, '')), 'new': str(patch[field])}
        audit_entries.append(AuditLog(
            user=request.user,
            action='UPDATE',
            model_name='Product',
            object_id=str(row['id']),
            object_repr=f'Product {row["id"]}',
            changes=json.dumps(changes),
        ))
    AuditLog.objects.bulk_create(audit_entries)

    return JsonResponse({
        'success': True,
        'updated_count': updated_count,
        'patch': patch,
    })

@require_permission('TRACKER', 'write')
@require_POST
def add_internal_note_api(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)
        
    content = data.get('content', '').strip()
    order_id = data.get('order_id')
    product_id = data.get('product_id')

    if not content:
        return JsonResponse({'success': False, 'error': 'Content cannot be empty.'}, status=400)
    
    order = get_object_or_404(Order, id=order_id) if order_id else None
    product = get_object_or_404(Product, id=product_id) if product_id else None

    if not order and not product:
        return JsonResponse({'success': False, 'error': 'Must specify order or product.'}, status=400)

    note = InternalNote.objects.create(
        author=request.user,
        order=order,
        product=product,
        content=content
    )

    if product:
        target_url = f"{reverse('tracker:order_detail', kwargs={'order_id': product.order.id})}?open_product={product.id}"
    elif order:
        target_url = reverse('tracker:order_detail', kwargs={'order_id': order.id})
    else:
        target_url = reverse('tracker:dashboard')

    AuditLog.objects.create(
        user=request.user,
        action='COMMENT',
        model_name='InternalNote',
        object_id=str(note.id),
        object_repr=f"Note on {note.order.order_number if note.order else note.product.item_name}",
        changes=json.dumps({'content': content[:200]}) if content else "Added comment"
    )

    # Parse mentions
    mentions = set(re.findall(r'@([\w.-]+)', content))
    from django.contrib.auth import get_user_model
    User = get_user_model()
    for username in mentions:
        try:
            mentioned_user = User.objects.get(username__iexact=username)
            if mentioned_user != request.user:
                Notification.objects.create(
                    user=mentioned_user,
                    title="You were mentioned in a note",
                    message=f"{request.user.username} mentioned you: '{content[:50]}...'",
                    link=target_url
                )
        except User.DoesNotExist:
            pass

    # Return response with author info to append locally
    return JsonResponse({
        'success': True, 
        'note': {
            'id': str(note.id),
            'content': note.content,
            'author_id': note.author.id,
            'author_name': note.author.get_full_name() or note.author.username,
            'is_deleted': note.is_deleted,
            'created_at': note.created_at.strftime("%b. %d, %Y, %I:%M %p").replace("AM", "a.m.").replace("PM", "p.m.")
        }
    })


@require_permission('TRACKER', 'write')
@require_POST
def bulk_add_internal_note_api(request):
    """
    Create the same InternalNote on multiple products at once.

    Request body (JSON):
        { "product_ids": ["uuid1", "uuid2", ...], "content": "Note text here" }

    Returns:
        { "success": true, "created_count": N }
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)

    product_ids = data.get('product_ids', [])
    content     = data.get('content', '').strip()

    if not product_ids:
        return JsonResponse({'success': False, 'error': 'No product IDs supplied.'}, status=400)

    if not content:
        return JsonResponse({'success': False, 'error': 'Note content cannot be empty.'}, status=400)

    # Validate products exist and belong to accessible scope
    products = list(Product.objects.filter(id__in=product_ids).select_related('order'))
    if not products:
        return JsonResponse({'success': False, 'error': 'No matching products found.'}, status=404)

    # Bulk-create one note per product
    notes = InternalNote.objects.bulk_create([
        InternalNote(author=request.user, product=p, content=content)
        for p in products
    ])

    # Log audit entries for bulk comments
    audit_entries = []
    for note in notes:
        audit_entries.append(AuditLog(
            user=request.user,
            action='COMMENT',
            model_name='InternalNote',
            object_id=str(note.id),
            object_repr=f"Note on {note.product.item_name}",
            changes=json.dumps({'content': content[:100]})
        ))
    AuditLog.objects.bulk_create(audit_entries)

    # Fire @mention notifications (deduplicated across all products)
    mentions = set(re.findall(r'@([\w.-]+)', content))
    if mentions:
        from django.contrib.auth import get_user_model
        DjangoUser = get_user_model()
        for username in mentions:
            try:
                mentioned_user = DjangoUser.objects.get(username__iexact=username)
                if mentioned_user != request.user:
                    Notification.objects.create(
                        user=mentioned_user,
                        title="You were mentioned in a bulk note",
                        message=f"{request.user.username} mentioned you in a note on {len(products)} product(s): '{content[:60]}…'",
                        link=reverse('tracker:order_detail', kwargs={'order_id': products[0].order.id})
                    )
            except DjangoUser.DoesNotExist:
                pass

    return JsonResponse({'success': True, 'created_count': len(notes)})

@require_permission('TRACKER', 'write')
def mark_notification_read_api(request, notification_id):
    notif = get_object_or_404(Notification, id=notification_id, user=request.user)
    notif.is_read = True
    notif.save()
    
    if notif.link:
        return redirect(notif.link)
    return redirect(reverse('tracker:dashboard'))

@require_permission('TRACKER', 'write')
def mark_all_notifications_read_api(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect(reverse('tracker:dashboard'))

@require_permission('TRACKER', 'write')
@require_POST
def edit_internal_note_api(request, note_id):
    note = get_object_or_404(InternalNote, id=note_id)
    if note.author != request.user:
        return JsonResponse({'success': False, 'error': 'You can only edit your own notes.'}, status=403)
        
    try:
        data = json.loads(request.body)
        content = data.get('content', '').strip()
        if not content:
            return JsonResponse({'success': False, 'error': 'Content cannot be empty.'}, status=400)
            
        note.content = content
        note.save()
        return JsonResponse({'success': True, 'content': note.content, 'updated_at': note.updated_at.strftime("%b. %d, %Y, %I:%M %p").replace("AM", "a.m.").replace("PM", "p.m.")})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@require_permission('TRACKER', 'write')
@require_POST
def delete_internal_note_api(request, note_id):
    note = get_object_or_404(InternalNote, id=note_id)
    
    if note.author != request.user and not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'success': False, 'error': 'You do not have permission to delete this note.'}, status=403)
        
    is_permanent = request.GET.get('permanent') == 'true'
    
    if is_permanent:
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({'success': False, 'error': 'Only administrators can permanently delete notes.'}, status=403)
        note.delete()
    else:
        note.is_deleted = True
        note.save()
        
    return JsonResponse({'success': True})

# Admin User Management
from django.contrib.auth import get_user_model
User = get_user_model()
from django.contrib.auth.decorators import user_passes_test
from .forms import AdminUserCreationForm, AdminUserChangeForm, AdminPasswordResetForm

def is_admin(user):
    return user.is_staff or user.is_superuser

@require_permission('TRACKER', 'read')
def user_activity_view(request):
    """User-specific activity panel showing their own immutable audit log."""
    user_logs = AuditLog.objects.select_related('user').filter(user=request.user).order_by('-timestamp')
    
    return render(request, 'tracker/user_activity.html', {
        'logs': user_logs[:500],
        'page_title': 'My Activity',
    })

@require_permission('TRACKER', 'read')
@user_passes_test(is_admin)
def audit_log_list(request):
    logs = AuditLog.objects.select_related('user').all()
    model_filter = request.GET.get('model')
    action_filter = request.GET.get('action')
    user_filter = request.GET.get('user')
    task_filter = request.GET.get('task')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if model_filter:
        logs = logs.filter(model_name=model_filter)
    if action_filter:
        logs = logs.filter(action=action_filter)
    if user_filter:
        logs = logs.filter(user_id=user_filter)
    if task_filter:
        logs = logs.filter(task_id=task_filter)
    if start_date:
        logs = logs.filter(timestamp__date__gte=start_date)
    if end_date:
        logs = logs.filter(timestamp__date__lte=end_date)
    
    # Get distinct models for filter dropdown
    models = AuditLog.objects.values_list('model_name', flat=True).order_by('model_name').distinct()
    # Get all users for filter dropdown
    users = User.objects.filter(is_active=True).order_by('username')
    # Get all tasks for filter dropdown
    tasks = Task.objects.select_related().order_by('-created_at')[:100]
    
    return render(request, 'tracker/audit_log.html', {
        'logs': logs[:500],
        'models': models,
        'users': users,
        'tasks': tasks,
        'current_model': model_filter,
        'current_action': action_filter,
        'current_user': user_filter,
        'current_task': task_filter,
        'start_date': start_date,
        'end_date': end_date,
    })

@require_permission('TRACKER', 'write')
@require_POST
@user_passes_test(is_admin)
def delete_audit_log(request, log_id):
    """Admin-only endpoint to delete an audit log entry."""
    log = get_object_or_404(AuditLog, id=log_id)
    log.delete()
    messages.success(request, "Audit log entry deleted.")
    return redirect('tracker:audit_log_list')

@require_permission('TRACKER', 'write')
@user_passes_test(is_admin)
def user_management_create(request):
    if request.method == 'POST':
        form = AdminUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"User '{user.username}' created successfully.")
            return redirect('tracker:user_management_list')
    else:
        form = AdminUserCreationForm()
    return render(request, 'tracker/user_form.html', {'form': form, 'title': 'Create New User'})

@require_permission('TRACKER', 'write')
@user_passes_test(is_admin)
def user_management_edit(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        form = AdminUserChangeForm(request.POST, instance=user_obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"User '{user_obj.username}' updated successfully.")
            return redirect('tracker:user_management_list')
    else:
        form = AdminUserChangeForm(instance=user_obj)
    return render(request, 'tracker/user_form.html', {'form': form, 'title': f'Edit User: {user_obj.username}', 'user_obj': user_obj})

@require_permission('TRACKER', 'write')
@require_POST
@user_passes_test(is_admin)
def user_management_delete(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    if user_obj == request.user:
        messages.error(request, "You cannot delete yourself.")
    else:
        username = user_obj.username
        user_obj.delete()
        messages.success(request, f"User '{username}' was deleted.")
    return redirect('tracker:user_management_list')

@require_permission('TRACKER', 'write')
@user_passes_test(is_admin)
def user_management_reset_password(request, user_id):
    user_obj = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        form = AdminPasswordResetForm(user_obj, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"Password reset for '{user_obj.username}'.")
            return redirect('tracker:user_management_list')
    else:
        form = AdminPasswordResetForm(user_obj)
    return render(request, 'tracker/user_reset_password.html', {'form': form, 'user_obj': user_obj})

@require_permission('TRACKER', 'read')
@user_passes_test(is_admin)
def user_management_list(request):
    users = User.objects.all().order_by('username')
    return render(request, 'tracker/user_list.html', {'users': users})

@require_permission('TRACKER', 'write')
def user_profile(request):
    from .forms import UserProfileForm
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated successfully.")
            return redirect('tracker:user_profile')
    else:
        form = UserProfileForm(instance=request.user)
    
    return render(request, 'tracker/user_profile.html', {'form': form})




def _process_price_update(request, product, new_buying_ex, new_buying_inc, new_selling_ex, new_selling_inc, new_gst, supplier_option=None):
    from decimal import Decimal
    from .models import PriceApprovalRequest, Notification
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    buying_inc = Decimal(str(new_buying_inc or 0))
    selling_inc = Decimal(str(new_selling_inc or 0))
    
    requires_approval = False
    
    if buying_inc > 1 and selling_inc > 1:
        if selling_inc > 0:
            margin = ((selling_inc - buying_inc) / selling_inc) * 100
        else:
            margin = Decimal('0.00')
            
        min_margin = getattr(product.order, 'minimum_profit_margin', Decimal('25.00'))
        if margin < min_margin:
            requires_approval = True
            
    if requires_approval:
        product.price_approval_requests.filter(status='PENDING').update(status='REJECTED')
        
        req = PriceApprovalRequest.objects.create(
            product=product,
            requested_by=request.user,
            buying_price_ex_gst=new_buying_ex,
            buying_price_inc_gst=new_buying_inc,
            selling_price_ex_gst=new_selling_ex,
            selling_price_inc_gst=new_selling_inc,
            gst_percentage=new_gst,
            supplier_option=supplier_option,
            status='PENDING'
        )
        
        superusers = User.objects.filter(is_superuser=True)
        for su in superusers:
            Notification.objects.create(
                user=su,
                title="Price Approval Required",
                message=f"A price update for '{product.item_name}' by {request.user.get_full_name() or request.user.username} requires approval.",
                link=f"/product/{product.id}/"
            )
        return {'requires_approval': True, 'request': req}
    else:
        product.buying_price_ex_gst = new_buying_ex
        product.buying_price_inc_gst = new_buying_inc
        product.selling_price_ex_gst = new_selling_ex
        product.selling_price_inc_gst = new_selling_inc
        product.gst_percentage = new_gst
        product.price_approved_by = None
        product.price_approved_at = None
        product.save()
        return {'requires_approval': False}

@require_permission('TRACKER', 'write')
def approve_price_request(request, request_id):
    from .models import PriceApprovalRequest, Notification
    from django.utils import timezone
    if not request.user.is_superuser:
        messages.error(request, "Permission denied.")
        return redirect('tracker:dashboard')
        
    req = get_object_or_404(PriceApprovalRequest, id=request_id)
    if req.status != 'PENDING':
        messages.error(request, f"This request is already {req.status}.")
        redirect_url = reverse('tracker:order_detail', kwargs={'order_id': req.product.order.id})
        lot_id = req.product.lot.id if req.product.lot else 'unassigned'
        return redirect(f"{redirect_url}?selected_product_id={req.product.id}&open_lot_id={lot_id}")
        
    if request.method == 'POST':
        req.product.buying_price_ex_gst = req.buying_price_ex_gst
        req.product.buying_price_inc_gst = req.buying_price_inc_gst
        req.product.selling_price_ex_gst = req.selling_price_ex_gst
        req.product.selling_price_inc_gst = req.selling_price_inc_gst
        req.product.gst_percentage = req.gst_percentage
        req.product.price_approved_by = request.user
        req.product.price_approved_at = timezone.now()
        req.product.save()
        
        req.status = 'APPROVED'
        req.reviewed_by = request.user
        req.save()
        
        if req.requested_by:
            Notification.objects.create(
                user=req.requested_by,
                title="Price Request Approved",
                message=f"Your price update for '{req.product.item_name}' was approved.",
                link=f"/product/{req.product.id}/"
            )
            
        messages.success(request, f"Price request for {req.product.item_name} approved and applied.")
        redirect_url = reverse('tracker:order_detail', kwargs={'order_id': req.product.order.id})
        lot_id = req.product.lot.id if req.product.lot else 'unassigned'
        return redirect(f"{redirect_url}?selected_product_id={req.product.id}&open_lot_id={lot_id}")
        
    redirect_url = reverse('tracker:order_detail', kwargs={'order_id': req.product.order.id})
    lot_id = req.product.lot.id if req.product.lot else 'unassigned'
    return redirect(f"{redirect_url}?selected_product_id={req.product.id}&open_lot_id={lot_id}")

@require_permission('TRACKER', 'write')
def reject_price_request(request, request_id):
    from .models import PriceApprovalRequest, Notification
    if not request.user.is_superuser:
        messages.error(request, "Permission denied.")
        return redirect('tracker:dashboard')
        
    req = get_object_or_404(PriceApprovalRequest, id=request_id)
    if req.status != 'PENDING':
        messages.error(request, f"This request is already {req.status}.")
        redirect_url = reverse('tracker:order_detail', kwargs={'order_id': req.product.order.id})
        lot_id = req.product.lot.id if req.product.lot else 'unassigned'
        return redirect(f"{redirect_url}?selected_product_id={req.product.id}&open_lot_id={lot_id}")
        
    if request.method == 'POST':
        req.status = 'REJECTED'
        req.reviewed_by = request.user
        req.save()
        
        if req.requested_by:
            Notification.objects.create(
                user=req.requested_by,
                title="Price Request Rejected",
                message=f"Your price update for '{req.product.item_name}' was rejected.",
                link=f"/product/{req.product.id}/"
            )
            
        messages.success(request, f"Price request for {req.product.item_name} rejected.")
        redirect_url = reverse('tracker:order_detail', kwargs={'order_id': req.product.order.id})
        lot_id = req.product.lot.id if req.product.lot else 'unassigned'
        return redirect(f"{redirect_url}?selected_product_id={req.product.id}&open_lot_id={lot_id}")
        
    redirect_url = reverse('tracker:order_detail', kwargs={'order_id': req.product.order.id})
    lot_id = req.product.lot.id if req.product.lot else 'unassigned'
    return redirect(f"{redirect_url}?selected_product_id={req.product.id}&open_lot_id={lot_id}")

@require_POST
@require_permission('TRACKER', 'write')
def api_create_lot(request, order_id):
    import json
    order = get_object_or_404(Order, id=order_id)
    try:
        data = json.loads(request.body)
        lot_name = data.get('lot_name', '').strip()
        if not lot_name:
            return JsonResponse({'success': False, 'error': 'Lot name is required.'})
        lot = Lot.objects.create(order=order, lot_name=lot_name, created_by=request.user)
        return JsonResponse({'success': True, 'lot_id': str(lot.id), 'lot_name': lot.lot_name})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ──────────────────────────────────────────────────────────────
#  Personal Notes API  (private — only the owning user can access)
# ──────────────────────────────────────────────────────────────
from .models import UserNote, UserTodo, UserReferenceDocument
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


@require_permission('TRACKER', 'read')
def api_notes_list_create(request):
    """GET → list user's notes; POST → create a note."""
    if request.method == 'GET':
        notes = UserNote.objects.filter(user=request.user).prefetch_related('documents')
        data = []
        for n in notes:
            docs = [{'id': str(d.id), 'url': d.document.url, 'name': d.document.name.split('/')[-1], 'reference_text': d.reference_text} for d in n.documents.all()]
            data.append({
                'id': str(n.id),
                'title': n.title,
                'content': n.content,
                'updated_at': n.updated_at.strftime('%Y-%m-%d %H:%M'),
                'documents': docs,
            })
        return JsonResponse({'notes': data})

    # POST
    is_multipart = request.content_type.startswith('multipart/form-data')
    if is_multipart:
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        files = request.FILES.getlist('documents')
        doc_refs = request.POST.getlist('document_references')
    else:
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)
        title = body.get('title', '').strip()
        content = body.get('content', '').strip()
        files = []
        doc_refs = []

    if not title:
        return JsonResponse({'success': False, 'error': 'Title is required.'}, status=400)

    note = UserNote.objects.create(
        user=request.user,
        title=title,
        content=content,
    )

    docs_data = []
    for i, f in enumerate(files):
        ref = doc_refs[i] if i < len(doc_refs) else ''
        doc = UserReferenceDocument.objects.create(user=request.user, note=note, document=f, reference_text=ref)
        docs_data.append({'id': str(doc.id), 'url': doc.document.url, 'name': doc.document.name.split('/')[-1], 'reference_text': doc.reference_text})

    return JsonResponse({
        'success': True,
        'note': {
            'id': str(note.id),
            'title': note.title,
            'content': note.content,
            'updated_at': note.updated_at.strftime('%Y-%m-%d %H:%M'),
            'documents': docs_data,
        }
    })


@require_permission('TRACKER', 'read')
def api_note_detail(request, note_id):
    """POST/PUT/PATCH → update; DELETE → delete. User can only touch their own notes."""
    note = get_object_or_404(UserNote, id=note_id, user=request.user)

    if request.method == 'DELETE':
        note.delete()
        return JsonResponse({'success': True})

    if request.method in ('PUT', 'PATCH', 'POST'):
        is_multipart = request.content_type.startswith('multipart/form-data')
        if is_multipart:
            title = request.POST.get('title', note.title).strip()
            content = request.POST.get('content', note.content)
            files = request.FILES.getlist('documents')
            doc_refs = request.POST.getlist('document_references')
        else:
            try:
                body = json.loads(request.body)
            except Exception:
                return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)
            title = body.get('title', note.title).strip() or note.title
            content = body.get('content', note.content)
            files = []
            doc_refs = []

        note.title = title or note.title
        note.content = content
        note.save()

        for i, f in enumerate(files):
            ref = doc_refs[i] if i < len(doc_refs) else ''
            UserReferenceDocument.objects.create(user=request.user, note=note, document=f, reference_text=ref)

        docs_data = [{'id': str(d.id), 'url': d.document.url, 'name': d.document.name.split('/')[-1], 'reference_text': d.reference_text} for d in note.documents.all()]

        return JsonResponse({
            'success': True,
            'note': {
                'id': str(note.id),
                'title': note.title,
                'content': note.content,
                'updated_at': note.updated_at.strftime('%Y-%m-%d %H:%M'),
                'documents': docs_data,
            }
        })

    return JsonResponse({'success': False, 'error': 'Method not allowed.'}, status=405)


# ──────────────────────────────────────────────────────────────
#  Personal To-Do API  (private — only the owning user can access)
# ──────────────────────────────────────────────────────────────

@require_permission('TRACKER', 'read')
def api_todos_list_create(request):
    """GET → list user's todos; POST → create a todo."""
    if request.method == 'GET':
        todos = UserTodo.objects.filter(user=request.user).prefetch_related('documents')
        data = []
        for t in todos:
            docs = [{'id': str(d.id), 'url': d.document.url, 'name': d.document.name.split('/')[-1], 'reference_text': d.reference_text} for d in t.documents.all()]
            data.append({
                'id': str(t.id),
                'title': t.title,
                'description': t.description,
                'is_completed': t.is_completed,
                'updated_at': t.updated_at.strftime('%Y-%m-%d %H:%M'),
                'documents': docs,
            })
        return JsonResponse({'todos': data})

    # POST
    is_multipart = request.content_type.startswith('multipart/form-data')
    if is_multipart:
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        files = request.FILES.getlist('documents')
        doc_refs = request.POST.getlist('document_references')
    else:
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)
        title = body.get('title', '').strip()
        description = body.get('description', '').strip()
        files = []
        doc_refs = []

    if not title:
        return JsonResponse({'success': False, 'error': 'Title is required.'}, status=400)

    todo = UserTodo.objects.create(
        user=request.user,
        title=title,
        description=description,
    )

    docs_data = []
    for i, f in enumerate(files):
        ref = doc_refs[i] if i < len(doc_refs) else ''
        doc = UserReferenceDocument.objects.create(user=request.user, todo=todo, document=f, reference_text=ref)
        docs_data.append({'id': str(doc.id), 'url': doc.document.url, 'name': doc.document.name.split('/')[-1], 'reference_text': doc.reference_text})

    return JsonResponse({
        'success': True,
        'todo': {
            'id': str(todo.id),
            'title': todo.title,
            'description': todo.description,
            'is_completed': todo.is_completed,
            'updated_at': todo.updated_at.strftime('%Y-%m-%d %H:%M'),
            'documents': docs_data,
        }
    })


@require_permission('TRACKER', 'read')
def api_todo_detail(request, todo_id):
    """POST/PUT/PATCH → toggle or update; DELETE → delete. User can only touch their own todos."""
    todo = get_object_or_404(UserTodo, id=todo_id, user=request.user)

    if request.method == 'DELETE':
        todo.delete()
        return JsonResponse({'success': True})

    if request.method in ('PUT', 'PATCH', 'POST'):
        is_multipart = request.content_type.startswith('multipart/form-data')
        if is_multipart:
            if 'is_completed' in request.POST:
                todo.is_completed = request.POST.get('is_completed') in ['true', '1', 'True']
            if 'title' in request.POST:
                todo.title = request.POST.get('title').strip() or todo.title
            if 'description' in request.POST:
                todo.description = request.POST.get('description')
            files = request.FILES.getlist('documents')
            doc_refs = request.POST.getlist('document_references')
        else:
            try:
                body = json.loads(request.body)
            except Exception:
                return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)

            if 'is_completed' in body:
                todo.is_completed = bool(body['is_completed'])
            if 'title' in body:
                todo.title = body['title'].strip() or todo.title
            if 'description' in body:
                todo.description = body['description']
            files = []
            doc_refs = []

        todo.save()

        for i, f in enumerate(files):
            ref = doc_refs[i] if i < len(doc_refs) else ''
            UserReferenceDocument.objects.create(user=request.user, todo=todo, document=f, reference_text=ref)

        docs_data = [{'id': str(d.id), 'url': d.document.url, 'name': d.document.name.split('/')[-1], 'reference_text': d.reference_text} for d in todo.documents.all()]

        return JsonResponse({ 
            'success': True,
            'todo': {
                'id': str(todo.id),
                'title': todo.title,
                'description': todo.description,
                'is_completed': todo.is_completed,
                'updated_at': todo.updated_at.strftime('%Y-%m-%d %H:%M'),
                'documents': docs_data,
            }
        })

    return JsonResponse({'success': False, 'error': 'Method not allowed.'}, status=405)

@require_permission('TRACKER', 'write')
def api_delete_reference_document(request, doc_id):
    doc = get_object_or_404(UserReferenceDocument, id=doc_id, user=request.user)
    if request.method == 'DELETE':
        doc.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Method not allowed.'}, status=405)


# ──────────────────────────────────────────────────────────────
#  Drag-and-Drop Reorder API
# ──────────────────────────────────────────────────────────────

@require_permission('TRACKER', 'write')
def api_reorder_products(request, order_id):
    """
    PATCH /api/order/<id>/reorder-products/
    Body: [{"id": "<uuid>", "sl_no": 1, "lot_id": "<uuid>|unassigned"}, ...]
    Updates sl_no (and optionally lot) for each product atomically.
    Only products belonging to the authenticated user's accessible order are updated.
    """
    if request.method != 'PATCH':
        return JsonResponse({'success': False, 'error': 'PATCH required.'}, status=405)

    order = get_object_or_404(Order, id=order_id)

    try:
        items = json.loads(request.body)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON.'}, status=400)

    if not isinstance(items, list):
        return JsonResponse({'success': False, 'error': 'Expected a list.'}, status=400)

    # Build a mapping of valid product IDs for this order
    product_ids = [item.get('id') for item in items if item.get('id')]
    products_map = {
        str(p.id): p
        for p in Product.objects.filter(order=order, id__in=product_ids)
    }

    lots_map = {str(l.id): l for l in order.lots.all()}

    updated = []
    for item in items:
        pid = str(item.get('id', ''))
        product = products_map.get(pid)
        if not product:
            continue

        sl_no = item.get('sl_no')
        lot_id = str(item.get('lot_id', ''))

        if sl_no is not None:
            product.sl_no = int(sl_no)

        if lot_id:
            if lot_id == 'unassigned':
                product.lot = None
            elif lot_id in lots_map:
                product.lot = lots_map[lot_id]

        product.save(update_fields=['sl_no', 'lot'])
        updated.append(pid)

    return JsonResponse({'success': True, 'updated': len(updated)})


# ──────────────────────────────────────────────────────────────
#  Per-Product Audit Trail API (for History tab in modal)
# ──────────────────────────────────────────────────────────────

@require_permission('TRACKER', 'write')
def api_product_audit_log(request, product_id):
    """
    GET /api/product/<id>/audit-log/
    Returns the last 50 AuditLog entries for a specific Product.
    """
    product = get_object_or_404(Product, id=product_id)

    logs = (
        AuditLog.objects
        .filter(model_name='Product', object_id=str(product_id))
        .select_related('user')
        .order_by('-timestamp')[:50]
    )

    data = []
    for log in logs:
        try:
            changes = json.loads(log.changes) if log.changes else {}
        except Exception:
            changes = {}

        data.append({
            'action': log.action,
            'user': log.user.get_full_name() or log.user.username if log.user else 'System',
            'timestamp': log.timestamp.strftime('%b %d, %Y %H:%M'),
            'changes': changes,
        })

    return JsonResponse({'logs': data})

import zipfile
import os
import shutil
from datetime import datetime
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from .models import SystemSetting

@user_passes_test(lambda u: u.is_superuser)
def system_backup(request):
    """Generates a zip file containing database_backup.json and media/ directory."""
    from django.core.management import call_command
    import tempfile
    import logging

    logger = logging.getLogger(__name__)

    tmp_dump_path = None
    tmp_zip_path = None

    try:
        media_root = settings.MEDIA_ROOT

        # Update last backup date
        setting, created = SystemSetting.objects.get_or_create(key='last_backup_date')
        setting.value = timezone.now().isoformat()
        setting.save()

        # Create temporary zip file on disk
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_zip:
            tmp_zip_path = tmp_zip.name

        with zipfile.ZipFile(tmp_zip_path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as zip_file:
            # Dump database to JSON
            with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.json', encoding='utf-8') as tmp_dump:
                tmp_dump_path = tmp_dump.name
                call_command(
                    'dumpdata',
                    '--natural-foreign',
                    '--natural-primary',
                    '--exclude', 'contenttypes',
                    '--exclude', 'auth.permission',
                    '--exclude', 'sessions',
                    '--exclude', 'admin.logentry',
                    format='json',
                    stdout=tmp_dump
                )
                tmp_dump.flush()

            zip_file.write(tmp_dump_path, 'database_backup.json')

            # Add media files
            if os.path.exists(media_root):
                for root, dirs, files in os.walk(media_root):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.join('media', os.path.relpath(file_path, media_root))
                        zip_file.write(file_path, arcname)

        current_date = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        filename = f"backup_{current_date}.zip"

        response = FileResponse(open(tmp_zip_path, 'rb'), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = os.path.getsize(tmp_zip_path)
        return response

    except Exception as e:
        logger.exception("System backup failed")
        messages.error(request, f"Backup failed: {str(e)}")
        referer = request.META.get('HTTP_REFERER', '')
        if 'system/admin/backup' in referer:
            return redirect('tracker:system_admin_backup')
        return redirect('tracker:dashboard')

    finally:
        if tmp_dump_path and os.path.exists(tmp_dump_path):
            try:
                os.remove(tmp_dump_path)
            except Exception:
                pass


@user_passes_test(lambda u: u.is_superuser)
def system_restore(request):
    """Restores database and media from a zip file."""
    if request.method == 'POST':
        if 'backup_file' not in request.FILES:
            messages.error(request, 'No backup file provided.')
            return redirect('tracker:dashboard')

        backup_file = request.FILES['backup_file']
        if not backup_file.name.endswith('.zip'):
            messages.error(request, 'Please upload a valid .zip backup file.')
            return redirect('tracker:dashboard')

        try:
            from django.core.management import call_command
            import tempfile
            from django.contrib.auth import get_user_model
            from django.db.models.signals import post_save
            from tracker.signals import create_user_field_visibility

            media_root = settings.MEDIA_ROOT
            User = get_user_model()

            with zipfile.ZipFile(backup_file, 'r') as zip_ref:
                # Extract database
                if 'database_backup.json' in zip_ref.namelist():
                    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.json') as tmp_dump:
                        with zip_ref.open('database_backup.json') as source:
                            shutil.copyfileobj(source, tmp_dump)
                        tmp_dump_path = tmp_dump.name

                    try:
                        post_save.disconnect(create_user_field_visibility, sender=User)
                    except Exception:
                        pass

                    call_command('flush', interactive=False)
                    call_command('loaddata', tmp_dump_path)

                    try:
                        post_save.connect(create_user_field_visibility, sender=User)
                    except Exception:
                        pass

                    os.remove(tmp_dump_path)
                elif 'db.sqlite3' in zip_ref.namelist():
                    raise Exception("This backup uses the old SQLite format, which cannot be directly restored into PostgreSQL.")

                # Extract media files
                # Clear existing media
                if os.path.exists(media_root):
                    for item in os.listdir(media_root):
                        item_path = os.path.join(media_root, item)
                        if os.path.isfile(item_path):
                            os.remove(item_path)
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                else:
                    os.makedirs(media_root)

                for file_info in zip_ref.filelist:
                    if file_info.filename.startswith('media/'):
                        zip_ref.extract(file_info, settings.BASE_DIR)

            messages.success(request, 'System restored successfully. Please MANUALLY RESTART the server to ensure all connections are refreshed.')
        except Exception as e:
            messages.error(request, f'Restore failed: {str(e)}')

    # If the request comes from the new backup tab, redirect there. Otherwise dashboard.
    referer = request.META.get('HTTP_REFERER', '')
    if 'system/admin/backup' in referer:
        return redirect('tracker:system_admin_backup')
    return redirect('tracker:dashboard')

@user_passes_test(lambda u: u.is_superuser)
def system_admin_backup_view(request):
    """Renders the backup and restore page."""
    return render(request, 'tracker/backup.html')


# ──────────────────────────────────────────────────────────────────────────────
#  Bulk Action: Add Supplier to selected products (ADDITIVE — never overwrites)
# ──────────────────────────────────────────────────────────────────────────────
@require_permission('TRACKER', 'write')
@require_POST
def bulk_add_supplier_api(request):
    """
    Additively append a new SupplierCostOption to every selected product.
    Existing supplier options are never touched.

    Request body (JSON):
        {
            "product_ids":    ["uuid1", "uuid2", ...],
            "supplier_name":  "Acme Corp",
            "location":       "Mumbai",       // optional
            "contact_number": "9876543210",   // optional
            "contact_email":  "a@acme.com",   // optional
            "base_price":     1200.00,        // optional, unit price ex-GST
            "gst_percentage": 18.0,           // optional, default 18
            "total_inc_gst":  1416.00,        // optional, unit price inc-GST
            "description":    "Notes…",       // optional
            "mark_as_selected": false         // optional — set this supplier as selected
        }

    Returns:
        { "success": true, "created_count": N, "skipped_duplicates": M }
    """
    from django.db import transaction

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON body.'}, status=400)

    product_ids    = data.get('product_ids', [])
    supplier_name  = (data.get('supplier_name') or '').strip()
    location       = (data.get('location') or '').strip()
    contact_number = (data.get('contact_number') or '').strip()
    contact_email  = (data.get('contact_email') or '').strip()
    description    = (data.get('description') or '').strip()
    mark_selected  = bool(data.get('mark_as_selected', False))

    try:
        base_price      = float(data.get('base_price') or 0)
        gst_percentage  = float(data.get('gst_percentage') or 18)
        total_inc_gst   = float(data.get('total_inc_gst') or 0)
    except (TypeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Prices must be numeric.'}, status=400)

    if not product_ids:
        return JsonResponse({'success': False, 'error': 'No product IDs supplied.'}, status=400)
    if not supplier_name:
        return JsonResponse({'success': False, 'error': 'Supplier name is required.'}, status=400)

    products = list(Product.objects.filter(id__in=product_ids).select_related('order'))
    if not products:
        return JsonResponse({'success': False, 'error': 'No matching products found.'}, status=404)

    # Find products that already have this supplier to avoid exact duplicates
    existing_pairs = set(
        SupplierCostOption.objects
        .filter(product__in=products, supplier_name__iexact=supplier_name)
        .values_list('product_id', flat=True)
    )
    skipped = len(existing_pairs)
    new_products = [p for p in products if p.id not in existing_pairs]

    if not new_products:
        return JsonResponse({
            'success': True,
            'created_count': 0,
            'skipped_duplicates': skipped,
            'message': f'Supplier "{supplier_name}" already exists on all selected products.',
        })

    try:
        with transaction.atomic():
            # If marking as selected, deselect all existing options for these products first
            if mark_selected:
                SupplierCostOption.objects.filter(
                    product__in=new_products, is_selected=True
                ).update(is_selected=False)

            new_options = SupplierCostOption.objects.bulk_create([
                SupplierCostOption(
                    product=p,
                    supplier_name=supplier_name,
                    location=location,
                    contact_number=contact_number,
                    contact_email=contact_email or None,
                    description=description,
                    base_price=base_price,
                    gst_percentage=gst_percentage,
                    total_inc_gst=total_inc_gst,
                    is_selected=mark_selected,
                    created_by=request.user,
                    updated_by=request.user,
                )
                for p in new_products
            ])

            # If selected, sync product buying price fields too
            if mark_selected and base_price > 0:
                ids_to_update = [p.id for p in new_products]
                Product.objects.filter(id__in=ids_to_update).update(
                    buying_price_ex_gst=base_price,
                    buying_price_inc_gst=total_inc_gst if total_inc_gst else base_price,
                    gst_percentage=gst_percentage,
                    updated_by=request.user,
                )

            # Audit log
            AuditLog.objects.bulk_create([
                AuditLog(
                    user=request.user,
                    action='CREATE',
                    model_name='SupplierCostOption',
                    object_id=str(opt.id),
                    object_repr=f'Supplier "{supplier_name}" added to {opt.product.item_name}',
                    changes=json.dumps({
                        'supplier_name': supplier_name,
                        'base_price': str(base_price),
                        'is_selected': mark_selected,
                        'action': 'bulk_add_supplier',
                    }),
                )
                for opt in new_options
            ])

    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Database error: {str(e)}'}, status=500)

    return JsonResponse({
        'success': True,
        'created_count': len(new_options),
        'skipped_duplicates': skipped,
    })


# ──────────────────────────────────────────────────────────────────────────────
#  Bulk Action: Update Selling Price / Profit Margin on selected products
# ──────────────────────────────────────────────────────────────────────────────
@require_permission('TRACKER', 'write')
@require_POST
def bulk_update_selling_price_api(request):
    """
    Apply a flat selling price OR a profit-margin percentage to selected products.

    Request body (JSON) — supply ONE of the two modes:
        Mode A — flat price:
            { "product_ids": [...], "mode": "flat",
              "selling_price_ex_gst": 1500.00,
              "selling_price_inc_gst": 1770.00,
              "gst_percentage": 18.0 }

        Mode B — margin percentage (calculated per-product from its buying_price_ex_gst):
            { "product_ids": [...], "mode": "margin",
              "margin_percent": 25.0,
              "gst_percentage": 18.0 }

    Returns:
        { "success": true, "updated_count": N, "skipped_no_price": K }
    """
    from django.db import transaction
    from decimal import Decimal, ROUND_HALF_UP

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON body.'}, status=400)

    product_ids = data.get('product_ids', [])
    mode        = (data.get('mode') or '').strip().lower()

    if not product_ids:
        return JsonResponse({'success': False, 'error': 'No product IDs supplied.'}, status=400)
    if mode not in ('flat', 'margin'):
        return JsonResponse({'success': False, 'error': 'mode must be "flat" or "margin".'}, status=400)

    try:
        gst_pct = Decimal(str(data.get('gst_percentage') or 18))
    except Exception:
        return JsonResponse({'success': False, 'error': 'gst_percentage must be numeric.'}, status=400)

    products = list(Product.objects.filter(id__in=product_ids))
    if not products:
        return JsonResponse({'success': False, 'error': 'No matching products found.'}, status=404)

    updated_count   = 0
    skipped_no_price = 0
    audit_entries   = []

    try:
        with transaction.atomic():
            for product in products:
                if mode == 'flat':
                    try:
                        sp_ex  = Decimal(str(data.get('selling_price_ex_gst') or 0))
                        sp_inc = Decimal(str(data.get('selling_price_inc_gst') or 0))
                    except Exception:
                        return JsonResponse({'success': False, 'error': 'Selling prices must be numeric.'}, status=400)

                    old_ex  = product.selling_price_ex_gst
                    old_inc = product.selling_price_inc_gst
                    product.selling_price_ex_gst  = sp_ex
                    product.selling_price_inc_gst = sp_inc
                    product.gst_percentage        = gst_pct
                    product.updated_by            = request.user
                    product.save(update_fields=[
                        'selling_price_ex_gst', 'selling_price_inc_gst',
                        'gst_percentage', 'updated_by', 'updated_at'
                    ])
                    audit_entries.append(AuditLog(
                        user=request.user,
                        action='UPDATE',
                        model_name='Product',
                        object_id=str(product.id),
                        object_repr=product.item_name,
                        changes=json.dumps({
                            'selling_price_ex_gst': {'old': str(old_ex), 'new': str(sp_ex)},
                            'selling_price_inc_gst': {'old': str(old_inc), 'new': str(sp_inc)},
                            'action': 'bulk_flat_price',
                        }),
                    ))
                    updated_count += 1

                else:  # margin mode
                    try:
                        margin_pct = Decimal(str(data.get('margin_percent') or 0))
                    except Exception:
                        return JsonResponse({'success': False, 'error': 'margin_percent must be numeric.'}, status=400)

                    buy_ex = product.buying_price_ex_gst
                    if not buy_ex or buy_ex <= 0:
                        skipped_no_price += 1
                        continue

                    sp_ex  = (buy_ex * (1 + margin_pct / 100)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    sp_inc = (sp_ex * (1 + gst_pct / 100)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

                    old_ex  = product.selling_price_ex_gst
                    old_inc = product.selling_price_inc_gst
                    product.selling_price_ex_gst  = sp_ex
                    product.selling_price_inc_gst = sp_inc
                    product.gst_percentage        = gst_pct
                    product.updated_by            = request.user
                    product.save(update_fields=[
                        'selling_price_ex_gst', 'selling_price_inc_gst',
                        'gst_percentage', 'updated_by', 'updated_at'
                    ])
                    audit_entries.append(AuditLog(
                        user=request.user,
                        action='UPDATE',
                        model_name='Product',
                        object_id=str(product.id),
                        object_repr=product.item_name,
                        changes=json.dumps({
                            'selling_price_ex_gst': {'old': str(old_ex), 'new': str(sp_ex)},
                            'selling_price_inc_gst': {'old': str(old_inc), 'new': str(sp_inc)},
                            'margin_percent': str(margin_pct),
                            'action': 'bulk_margin_price',
                        }),
                    ))
                    updated_count += 1

            AuditLog.objects.bulk_create(audit_entries)

    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Database error: {str(e)}'}, status=500)

    return JsonResponse({
        'success': True,
        'updated_count': updated_count,
        'skipped_no_price': skipped_no_price,
    })


# ──────────────────────────────────────────────────────────────────────────────
#  Bulk Action: Update Customer Stage and/or Supplier Stage on selected products
# ──────────────────────────────────────────────────────────────────────────────
@require_permission('TRACKER', 'write')
@require_POST
def bulk_update_stages_api(request):
    """
    Set customer_stage and/or supplier_stage on multiple products at once.
    Passing an empty string clears the stage for that side.

    Request body (JSON):
        {
            "product_ids":     ["uuid1", "uuid2", ...],
            "customer_stage":  "PO_RECEIVED",   // optional, pass "" to clear
            "supplier_stage":  "QUOT_RECEIVED"  // optional, pass "" to clear
        }

    Returns:
        { "success": true, "updated_count": N }
    """
    from django.db import transaction

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON body.'}, status=400)

    product_ids     = data.get('product_ids', [])
    customer_stage  = data.get('customer_stage')   # None means "not supplied"
    supplier_stage  = data.get('supplier_stage')   # None means "not supplied"

    if not product_ids:
        return JsonResponse({'success': False, 'error': 'No product IDs supplied.'}, status=400)

    # At least one stage must be provided
    if customer_stage is None and supplier_stage is None:
        return JsonResponse({'success': False, 'error': 'Supply at least one of customer_stage or supplier_stage.'}, status=400)

    # Validate choices
    valid_customer = {k for k, _ in Product.CUSTOMER_STAGE_CHOICES} | {''}
    valid_supplier = {k for k, _ in Product.SUPPLIER_STAGE_CHOICES} | {''}

    if customer_stage is not None and customer_stage not in valid_customer:
        return JsonResponse({'success': False, 'error': f'Invalid customer_stage: {customer_stage}'}, status=400)
    if supplier_stage is not None and supplier_stage not in valid_supplier:
        return JsonResponse({'success': False, 'error': f'Invalid supplier_stage: {supplier_stage}'}, status=400)

    products_qs = Product.objects.filter(id__in=product_ids)
    if not products_qs.exists():
        return JsonResponse({'success': False, 'error': 'No matching products found.'}, status=404)

    update_fields = {'updated_by': request.user}
    if customer_stage is not None:
        update_fields['customer_stage'] = customer_stage or None
    if supplier_stage is not None:
        update_fields['supplier_stage'] = supplier_stage or None

    # Snapshot for audit
    audit_field_names = []
    if customer_stage is not None:
        audit_field_names.append('customer_stage')
    if supplier_stage is not None:
        audit_field_names.append('supplier_stage')

    snapshots = list(products_qs.values('id', 'item_name', *audit_field_names))

    try:
        with transaction.atomic():
            updated_count = products_qs.update(**update_fields)

            audit_entries = []
            for row in snapshots:
                changes = {}
                if customer_stage is not None:
                    changes['customer_stage'] = {
                        'old': row.get('customer_stage') or '',
                        'new': customer_stage,
                    }
                if supplier_stage is not None:
                    changes['supplier_stage'] = {
                        'old': row.get('supplier_stage') or '',
                        'new': supplier_stage,
                    }
                changes['action'] = 'bulk_update_stages'
                audit_entries.append(AuditLog(
                    user=request.user,
                    action='UPDATE',
                    model_name='Product',
                    object_id=str(row['id']),
                    object_repr=row['item_name'],
                    changes=json.dumps(changes),
                ))
            AuditLog.objects.bulk_create(audit_entries)

    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Database error: {str(e)}'}, status=500)

    return JsonResponse({'success': True, 'updated_count': updated_count})


@require_POST
@require_permission('TRACKER', 'write')
def add_order_expense_api(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    try:
        data = json.loads(request.body)
        expense = OrderExpense.objects.create(
            order=order,
            expense_name=data.get('expense_name', ''),
            amount_ex_gst=data.get('amount_ex_gst', 0),
            gst_percentage=data.get('gst_percentage', 18),
            amount_inc_gst=data.get('amount_inc_gst', 0),
            remark=data.get('remark', ''),
            created_by=request.user
        )
        return JsonResponse({'success': True, 'expense_id': str(expense.id)})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@require_POST
@require_permission('TRACKER', 'write')
def edit_order_expense_api(request, expense_id):
    expense = get_object_or_404(OrderExpense, id=expense_id)
    try:
        data = json.loads(request.body)
        expense.expense_name = data.get('expense_name', expense.expense_name)
        expense.amount_ex_gst = data.get('amount_ex_gst', expense.amount_ex_gst)
        expense.gst_percentage = data.get('gst_percentage', expense.gst_percentage)
        expense.amount_inc_gst = data.get('amount_inc_gst', expense.amount_inc_gst)
        expense.remark = data.get('remark', expense.remark)
        expense.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@require_POST
@require_permission('TRACKER', 'write')
def delete_order_expense_api(request, expense_id):
    expense = get_object_or_404(OrderExpense, id=expense_id)
    try:
        expense.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
@require_POST
@require_permission('TRACKER', 'write')
def api_rename_lot(request, order_id):
    try:
        data = json.loads(request.body)
        lot_id = data.get('lot_id')
        new_name = data.get('new_name', '').strip()
        
        if not new_name:
            return JsonResponse({'success': False, 'error': 'Lot name cannot be empty.'})
            
        order = get_object_or_404(Order, id=order_id)
        
        if lot_id == 'unassigned':
            # Create a new lot and assign all unassigned products in this order to it
            new_lot = Lot.objects.create(
                order=order,
                lot_name=new_name,
                created_by=request.user
            )
            Product.objects.filter(order=order, lot__isnull=True).update(lot=new_lot)
        else:
            # Rename existing lot
            lot = get_object_or_404(Lot, id=lot_id, order=order)
            lot.lot_name = new_name
            lot.save()
            
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ─── Kanban / Pipeline Board ──────────────────────────────────────────────────

@require_permission('TRACKER', 'read')
def kanban_board_view(request):
    """
    Kanban pipeline board for Orders.
    Orders are displayed as draggable cards in status swimlanes.
    Status updates are handled by the existing update_order_status_api endpoint.
    """
    statuses = ['OPEN', 'SOURCING', 'PROCURED', 'SHIPPED', 'CLOSED']
    status_labels = {
        'OPEN': 'Open',
        'SOURCING': 'Sourcing',
        'PROCURED': 'Procured',
        'SHIPPED': 'Shipped',
        'CLOSED': 'Closed',
    }
    status_colors = {
        'OPEN':     '#6366f1',   # indigo
        'SOURCING': '#f59e0b',   # amber
        'PROCURED': '#3b82f6',   # blue
        'SHIPPED':  '#8b5cf6',   # violet
        'CLOSED':   '#10b981',   # emerald
    }

    all_orders = (
        Order.objects
        .prefetch_related('products', 'lots')
        .select_related('created_by')
        .order_by('-created_at')
    )

    # Build JSON-serializable data for each order card
    columns = []
    for status in statuses:
        orders_in_col = all_orders.filter(order_status=status)
        cards = []
        for o in orders_in_col:
            products_qs = o.products.all()
            product_count = products_qs.count()
            total_value = sum(
                float(p.selling_price_inc_gst or 0) * int(p.quantity or 0)
                for p in products_qs
            )
            cards.append({
                'id': str(o.id),
                'order_number': o.order_number,
                'customer_name': o.customer_name,
                'customer_phone': o.customer_phone,
                'product_count': product_count,
                'total_value': total_value,
                'payment_status': o.payment_status,
                'created_by': o.created_by.get_full_name() if o.created_by else '—',
                'order_date': o.order_date.strftime('%d %b %Y') if o.order_date else '',
                'remark': (o.remark or '')[:80],
                'detail_url': reverse('tracker:order_detail', args=[o.id]),
            })

        columns.append({
            'status': status,
            'label': status_labels[status],
            'color': status_colors[status],
            'cards': cards,
            'count': len(cards),
        })

    context = {
        'columns': columns,
        'columns_json': json.dumps(columns),
        'total_orders': all_orders.count(),
        'open_count': all_orders.filter(order_status='OPEN').count(),
    }
    return render(request, 'tracker/kanban_board.html', context)


# ─── Vendor Request for Quotation (RFQ) System ────────────────────────────────

@require_permission('TRACKER', 'write')
@require_POST
def create_vendor_rfq_api(request, order_id):
    """
    Generate a secure tokenized Vendor RFQ link for an order.
    Optionally filters specific products and notifies the vendor.
    """
    from .models import VendorRFQ
    order = get_object_or_404(Order, id=order_id)
    try:
        data = json.loads(request.body)
        supplier_name = data.get('supplier_name', '').strip()
        if not supplier_name:
            return JsonResponse({'success': False, 'error': 'Supplier name is required.'}, status=400)

        supplier_email = data.get('supplier_email', '').strip()
        supplier_phone = data.get('supplier_phone', '').strip()
        notes = data.get('notes', '').strip()
        product_ids = data.get('product_ids', [])

        products = list(Product.objects.filter(id__in=product_ids, order=order)) if product_ids else list(order.products.all())

        rfq = VendorRFQ.create_rfq(
            order=order,
            supplier_name=supplier_name,
            supplier_email=supplier_email,
            supplier_phone=supplier_phone,
            products=products,
            notes=notes,
            user=request.user
        )

        site_url = request.build_absolute_uri('/')[:-1]
        rfq_url = f"{site_url}/tracker/rfq/v/{rfq.token}/"

        # Formatted WhatsApp message for sending to supplier
        whatsapp_msg = (
            f"*REQUEST FOR QUOTATION (RFQ) — ODTECH SOLUTIONS*\n"
            f"---------------------------------------\n"
            f"Dear *{supplier_name}*,\n\n"
            f"Please submit your best price and delivery time for our enquiry (*{order.order_number}*):\n\n"
            f"🔗 *Open RFQ & Submit Price:* \n{rfq_url}\n\n"
            f"Total Items: {len(products)}\n\n"
            f"Best Regards,\n"
            f"*ODtech Solutions*"
        )

        return JsonResponse({
            'success': True,
            'rfq_id': str(rfq.id),
            'rfq_url': rfq_url,
            'whatsapp_msg': whatsapp_msg,
            'supplier_phone': supplier_phone,
        })
    except Exception as e:
        logger.error("create_vendor_rfq_api error: %s", e, exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_permission('TRACKER', 'read')
def list_vendor_rfqs_api(request, order_id):
    """List all RFQs generated for a given order."""
    from .models import VendorRFQ
    order = get_object_or_404(Order, id=order_id)
    rfqs = order.rfqs.prefetch_related('products').all()
    
    site_url = request.build_absolute_uri('/')[:-1]
    data = []
    for r in rfqs:
        data.append({
            'id': str(r.id),
            'supplier_name': r.supplier_name,
            'supplier_email': r.supplier_email or '',
            'supplier_phone': r.supplier_phone or '',
            'status': r.status,
            'status_display': r.get_status_display(),
            'item_count': r.products.count(),
            'created_at': r.created_at.strftime('%d %b %Y, %I:%M %p'),
            'submitted_at': r.submitted_at.strftime('%d %b %Y, %I:%M %p') if r.submitted_at else '—',
            'delivery_timeline': r.delivery_timeline or '—',
            'quote_reference_no': r.quote_reference_no or '—',
            'rfq_url': f"{site_url}/tracker/rfq/v/{r.token}/",
        })
    return JsonResponse({'success': True, 'rfqs': data})


@require_permission('TRACKER', 'write')
@require_POST
def delete_vendor_rfq_api(request, rfq_id):
    """
    Delete an RFQ record.
    Also removes corresponding SupplierCostOption quotes submitted under this RFQ.
    """
    from .models import VendorRFQ, SupplierCostOption
    rfq = get_object_or_404(VendorRFQ, id=rfq_id)
    order_id = rfq.order_id
    supplier_name = rfq.supplier_name

    try:
        # Clean up any cost options created with this RFQ quote reference or supplier
        if rfq.quote_reference_no:
            SupplierCostOption.objects.filter(
                product__order_id=order_id,
                supplier_name=supplier_name,
                description__icontains=rfq.quote_reference_no
            ).delete()
        elif rfq.status == 'SUBMITTED':
            # Fallback delete for submitted options matching supplier and RFQ description
            SupplierCostOption.objects.filter(
                product__order_id=order_id,
                supplier_name=supplier_name,
                description__icontains="Submitted via RFQ"
            ).delete()

        rfq.delete()
        return JsonResponse({'success': True, 'message': f'RFQ for {supplier_name} deleted successfully.'})
    except Exception as e:
        logger.error("delete_vendor_rfq_api error: %s", e, exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ─── Public Supplier Quoting Portal (No Login Required) ──────────────────────

def public_vendor_rfq_portal(request, token):
    """
    Public web portal for suppliers to submit their quotations securely.
    Suppliers view items, enter base prices, GST %, delivery lead times,
    and attach quotation documents.
    """
    from decimal import Decimal
    from django.utils import timezone
    from django.db import transaction
    import logging
    _logger = logging.getLogger(__name__)

    from .models import VendorRFQ, SupplierCostOption
    from config.models import CompanyProfile

    rfq = get_object_or_404(VendorRFQ, token=token)
    company = CompanyProfile.objects.first()
    products = rfq.products.all()

    if request.method == 'POST':
        if rfq.status == 'EXPIRED':
            messages.error(request, 'This RFQ has expired.')
            return redirect('tracker:public_vendor_rfq_portal', token=token)

        try:
            with transaction.atomic():
                quote_ref = request.POST.get('quote_reference_no', '').strip()
                lead_time = request.POST.get('delivery_timeline', '').strip()
                vendor_notes = request.POST.get('supplier_notes', '').strip()
                location = request.POST.get('location', '').strip()
                contact_phone = (request.POST.get('supplier_phone') or rfq.supplier_phone or '').strip()
                contact_email = (request.POST.get('supplier_email') or rfq.supplier_email or '').strip()

                rfq.quote_reference_no = quote_ref
                rfq.delivery_timeline = lead_time
                rfq.supplier_notes = vendor_notes
                if contact_phone:
                    rfq.supplier_phone = contact_phone
                if contact_email:
                    rfq.supplier_email = contact_email
                rfq.submitted_at = timezone.now()
                rfq.status = 'SUBMITTED'
                rfq.save()

                # Process per-item prices
                for p in products:
                    base_price_val = request.POST.get(f'price_{p.id}', '').strip()
                    gst_val = request.POST.get(f'gst_{p.id}', '18').strip()
                    item_desc = request.POST.get(f'desc_{p.id}', '').strip()

                    if base_price_val:
                        try:
                            base_price = Decimal(base_price_val)
                            gst_pct = Decimal(gst_val or '18')
                            total_inc = base_price * (Decimal('1') + gst_pct / Decimal('100'))

                            # Save as SupplierCostOption under this Product
                            opt = SupplierCostOption.objects.create(
                                product=p,
                                supplier_name=rfq.supplier_name,
                                contact_number=contact_phone or None,
                                contact_email=contact_email or None,
                                location=location or None,
                                base_price=base_price,
                                gst_percentage=gst_pct,
                                total_inc_gst=total_inc,
                                description=f"Submitted via RFQ {quote_ref or ''}: {item_desc}".strip(),
                            )

                            # Handle uploaded quotation file if provided for this item or order
                            uploaded_file = request.FILES.get(f'doc_{p.id}') or request.FILES.get('quote_document')
                            if uploaded_file:
                                opt.photo_or_document = uploaded_file
                                opt.save()

                        except Exception as parse_err:
                            _logger.warning("Error parsing item price: %s", parse_err)

                # Send in-app notification & alert
                from .models import Notification
                try:
                    target_user = rfq.created_by or User.objects.filter(is_superuser=True).first()
                    if target_user:
                        Notification.objects.create(
                            user=target_user,
                            title=f"Quote Received: {rfq.supplier_name}",
                            message=f"Supplier {rfq.supplier_name} submitted quotation for Order {rfq.order.order_number}.",
                            link=reverse('tracker:order_detail', args=[rfq.order.id])
                        )
                except Exception:
                    pass

            return render(request, 'tracker/rfq_thank_you.html', {
                'rfq': rfq,
                'company': company,
            })

        except Exception as e:
            _logger.error("public_vendor_rfq_portal POST error: %s", e, exc_info=True)
            messages.error(request, f"Error saving your quotation: {e}")

    return render(request, 'tracker/public_rfq_portal.html', {
        'rfq': rfq,
        'order': rfq.order,
        'products': products,
        'company': company,
    })
