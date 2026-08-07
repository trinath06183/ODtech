from core.decorators import require_permission
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from core.decorators import login_required, role_required, require_permission
from contacts.models import Contact
from .models import Payment


@require_permission('PAYMENTS', 'read')
def payment_list(request):
    page_num = request.GET.get('page', 1)
    payments = Payment.objects.select_related('contact').order_by('-date', '-id')
    total = payments.aggregate(t=Sum('amount'))['t'] or 0
    total_count = payments.count()

    paginator = Paginator(payments, 30)
    page_obj = paginator.get_page(page_num)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        rows_html = render_to_string(
            'payments/partials/payment_rows.html',
            {'payments': page_obj, 'request': request},
            request=request,
        )
        return JsonResponse({
            'html': rows_html,
            'has_next': page_obj.has_next(),
            'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
        })

    return render(request, 'payments/payment_list.html', {
        'payments': page_obj,
        'total': total,
        'total_count': total_count,
        'has_next': page_obj.has_next(),
        'next_page': 2 if page_obj.has_next() else None,
    })


@require_permission('PAYMENTS', 'write')
def payment_create(request):
    contacts  = Contact.objects.all().order_by('name')
    from documents.models import Document
    documents = Document.objects.filter(type__in=['INV', 'PRO', 'QTN', 'PO']).order_by('-id')

    # Pre-select contact and document if passed as query param
    preselect_contact = request.GET.get('contact', '')
    preselect_document = request.GET.get('document', '')

    if request.method == 'POST':
        contact_id = request.POST.get('contact')
        document_ref = request.POST.get('document_ref', '').strip() or None
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
                document_ref=document_ref,
                amount=amount,
                payment_mode=payment_mode,
                reference_number=reference_number,
                notes=notes,
            )
            messages.success(request, 'Payment recorded successfully.')
            return redirect('payment_list')

    return render(request, 'payments/payment_form.html', {
        'contacts': contacts,
        'documents': documents,
        'payment_modes': Payment.PAYMENT_MODES,
        'preselect_contact': preselect_contact,
        'preselect_document': preselect_document,
    })


@require_permission('PAYMENTS', 'write')
def payment_delete(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    if request.method == 'POST':
        payment.delete()
        messages.success(request, 'Payment deleted.')
    next_url = request.GET.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('payment_list')

# ==============================================================================
# EXPENSE MANAGEMENT VIEWS
# ==============================================================================
from django.utils import timezone
from .models import Expense
from .forms import ExpenseForm

from django.db.models import Q, Sum

@require_permission('PAYMENTS', 'read')
def expense_list(request):
    expenses = Expense.objects.all()

    search = request.GET.get('search', '').strip()
    category = request.GET.get('category', '').strip()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    employee_code = request.GET.get('employee_code', '').strip()
    sort = request.GET.get('sort', '').strip()

    if search:
        expenses = expenses.filter(
            Q(title__icontains=search) | 
            Q(notes__icontains=search) |
            Q(submitted_by__empid__icontains=search) |
            Q(submitted_by__username__icontains=search) |
            Q(submitted_by__first_name__icontains=search) |
            Q(submitted_by__last_name__icontains=search) |
            Q(expense_type__icontains=search)
        )
    if category:
        expenses = expenses.filter(expense_type=category)
    if start_date:
        expenses = expenses.filter(date__gte=start_date)
    if end_date:
        expenses = expenses.filter(date__lte=end_date)
    if employee_code:
        User = get_user_model()
        matching_users = User.objects.filter(
            Q(first_name__icontains=employee_code) |
            Q(last_name__icontains=employee_code) |
            Q(username__icontains=employee_code)
        ).values_list('empid', flat=True)
        
        expenses = expenses.filter(
            Q(employee_code__icontains=employee_code) |
            Q(employee_code__in=matching_users)
        )
        
    expenses = expenses.distinct()
        
    if sort == 'amount_asc':
        expenses = expenses.order_by('amount')
    elif sort == 'amount_desc':
        expenses = expenses.order_by('-amount')
    elif sort == 'date_asc':
        expenses = expenses.order_by('date')
    elif sort == 'date_desc':
        expenses = expenses.order_by('-date')
    elif sort == 'name_asc':
        expenses = expenses.order_by('title')
    elif sort == 'name_desc':
        expenses = expenses.order_by('-title')
    elif sort == 'status_asc':
        expenses = expenses.order_by('status')
    elif sort == 'status_desc':
        expenses = expenses.order_by('-status')
    else:
        expenses = expenses.order_by('-created_at')

    calc_expenses = expenses.exclude(status='Pending').exclude(status='Rejected')
    total_expenses = calc_expenses.aggregate(total=Sum('amount'))['total'] or 0
    total_paid = calc_expenses.filter(is_paid=True).aggregate(total=Sum('amount'))['total'] or 0
    total_unpaid = calc_expenses.filter(is_paid=False).aggregate(total=Sum('amount'))['total'] or 0

    page_num = request.GET.get('page', 1)
    total_count = expenses.count()
    paginator = Paginator(expenses, 30)
    page_obj = paginator.get_page(page_num)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        rows_html = render_to_string(
            'payments/partials/expense_rows.html',
            {'expenses': page_obj, 'request': request},
            request=request,
        )
        return JsonResponse({
            'html': rows_html,
            'has_next': page_obj.has_next(),
            'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
        })

    return render(request, 'payments/expense_list.html', {
        'expenses': page_obj,
        'expense_types': Expense.EXPENSE_TYPES,
        'total_expenses': total_expenses,
        'total_paid': total_paid,
        'total_unpaid': total_unpaid,
        'total_count': total_count,
        'has_next': page_obj.has_next(),
        'next_page': 2 if page_obj.has_next() else None,
    })

@require_permission('PAYMENTS', 'write')
def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.submitted_by = request.user
            
            # Extract payload fields
            payload = {}
            for key in request.POST.keys():
                if key.startswith('payload_'):
                    values = request.POST.getlist(key)
                    values = [v.strip() for v in values if v.strip()]
                    if not values:
                        continue
                    clean_key = key.replace('payload_', '')
                    if clean_key.endswith('[]'):
                        payload[clean_key[:-2]] = values
                    elif len(values) > 1:
                        payload[clean_key] = values
                    else:
                        payload[clean_key] = values[0]
            expense.payload = payload
            
            expense.save()
            messages.success(request, 'Expense submitted successfully.')
            return redirect('expense_list')
    else:
        form = ExpenseForm()
    return render(request, 'payments/expense_form.html', {'form': form, 'title': 'Submit New Expense'})

@require_permission('PAYMENTS', 'write')
def expense_edit(request, pk):
    if request.user.is_superuser:
        expense = get_object_or_404(Expense, pk=pk)
    else:
        expense = get_object_or_404(Expense, pk=pk, submitted_by=request.user)
        
    if expense.status != 'Pending' and not request.user.is_superuser:
        messages.error(request, 'You can only edit pending expenses.')
        return redirect('expense_list')
        
    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES, instance=expense)
        if form.is_valid():
            expense = form.save(commit=False)
            
            # Extract payload fields
            payload = {}
            for key in request.POST.keys():
                if key.startswith('payload_'):
                    values = request.POST.getlist(key)
                    values = [v.strip() for v in values if v.strip()]
                    if not values:
                        continue
                    clean_key = key.replace('payload_', '')
                    if clean_key.endswith('[]'):
                        payload[clean_key[:-2]] = values
                    elif len(values) > 1:
                        payload[clean_key] = values
                    else:
                        payload[clean_key] = values[0]
            expense.payload = payload
            
            expense.save()
            messages.success(request, 'Expense updated successfully.')
            return redirect('expense_list')
    else:
        form = ExpenseForm(instance=expense)
    return render(request, 'payments/expense_form.html', {'form': form, 'title': 'Edit Expense', 'expense': expense})

@require_permission('PAYMENTS', 'read')
def expense_detail(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
        
    return render(request, 'payments/expense_detail.html', {'title': 'View Expense', 'expense': expense})

@require_permission('PAYMENTS', 'write')
def expense_delete(request, pk):
    if request.user.is_superuser:
        expense = get_object_or_404(Expense, pk=pk)
    else:
        expense = get_object_or_404(Expense, pk=pk, submitted_by=request.user)
        
    if not request.user.is_superuser and expense.status != 'Pending':
        messages.error(request, 'You can only delete pending expenses.')
        return redirect('expense_list')
        
    if request.method == 'POST':
        expense.delete()
        messages.success(request, 'Expense deleted.')
    return redirect('expense_list')

@require_permission('PAYMENTS', 'write')
def expense_mark_paid(request, pk):
    expense = get_object_or_404(Expense, pk=pk, status='Approved', is_paid=False)
    # Only submitter or admin can mark as paid
    if not request.user.is_superuser and expense.submitted_by != request.user:
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('expense_list')
        
    if request.method == 'POST':
        expense.is_paid = True
        expense.paid_at = timezone.now()
        expense.save()
        messages.success(request, 'Expense marked as Paid.')
    return redirect('expense_list')

@require_permission('PAYMENTS', 'write')
@user_passes_test(lambda u: u.is_superuser)
def expense_approve(request, pk, status):
    expense = get_object_or_404(Expense, pk=pk)
    if status in ['Approved', 'Rejected']:
        expense.status = status
        expense.approved_by = request.user
        expense.approved_at = timezone.now()
        expense.save()
        messages.success(request, f'Expense {status.lower()} successfully.')
    return redirect('expense_list')

@require_permission('PAYMENTS', 'read')
def employee_code_autocomplete(request):
    query = request.GET.get('q', '').strip()
    User = get_user_model()
    if query:
        users = User.objects.filter(
            Q(empid__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(username__icontains=query),
            is_active=True
        ).exclude(empid__isnull=True).exclude(empid='')[:10]
        results = [{'code': u.empid, 'name': f"{u.get_full_name()} ({u.username})".strip()} for u in users]
    else:
        results = []
    return JsonResponse(results, safe=False)


import csv
from django.http import HttpResponse

@require_permission('PAYMENTS', 'read')
def payment_export_csv(request):
    """Export payments list to CSV."""
    from payments.models import Payment
    payment_type = request.GET.get('type', 'All')
    q = request.GET.get('q', '').strip()
    
    payments = Payment.objects.select_related('contact').all().order_by('-date', '-created_at')
    
    if payment_type != 'All':
        payments = payments.filter(payment_type=payment_type)
    if q:
        payments = payments.filter(
            Q(receipt_number__icontains=q) |
            Q(contact__name__icontains=q) |
            Q(document_ref__icontains=q)
        )

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="payments_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Receipt No.', 'Type', 'Contact', 'Amount', 'Mode', 'Reference'])
    
    for p in payments:
        writer.writerow([
            p.date.strftime('%d-%b-%Y') if p.date else '',
            p.receipt_number,
            p.get_payment_type_display(),
            p.contact.name if p.contact else '',
            p.amount,
            p.get_mode_display(),
            p.document_ref or ''
        ])
        
    return response

@require_permission('PAYMENTS', 'read')
def expense_export_csv(request):
    """Export expenses list to CSV."""
    from payments.models import Expense
    from django.urls import reverse
    import csv
    search = request.GET.get('search', '').strip()
    category = request.GET.get('category', '').strip()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    employee_code = request.GET.get('employee_code', '').strip()
    sort = request.GET.get('sort', '').strip()
    status = request.GET.get('status', 'All')
    
    expenses = Expense.objects.select_related('submitted_by').all()
    
    if search:
        expenses = expenses.filter(
            Q(title__icontains=search) | 
            Q(notes__icontains=search) |
            Q(submitted_by__empid__icontains=search) |
            Q(submitted_by__username__icontains=search) |
            Q(submitted_by__first_name__icontains=search) |
            Q(submitted_by__last_name__icontains=search) |
            Q(expense_type__icontains=search)
        )
    if category and category != 'All':
        expenses = expenses.filter(expense_type=category)
    if start_date:
        expenses = expenses.filter(date__gte=start_date)
    if end_date:
        expenses = expenses.filter(date__lte=end_date)
    if employee_code:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        matching_users = User.objects.filter(
            Q(first_name__icontains=employee_code) |
            Q(last_name__icontains=employee_code) |
            Q(username__icontains=employee_code)
        ).values_list('empid', flat=True)
        
        expenses = expenses.filter(
            Q(employee_code__icontains=employee_code) |
            Q(employee_code__in=matching_users)
        )
        
    if status != 'All':
        expenses = expenses.filter(status=status)
        
    expenses = expenses.distinct()
        
    if sort == 'amount_asc':
        expenses = expenses.order_by('amount')
    elif sort == 'amount_desc':
        expenses = expenses.order_by('-amount')
    elif sort == 'date_asc':
        expenses = expenses.order_by('date')
    elif sort == 'date_desc':
        expenses = expenses.order_by('-date')
    elif sort == 'name_asc':
        expenses = expenses.order_by('title')
    elif sort == 'name_desc':
        expenses = expenses.order_by('-title')
    elif sort == 'status_asc':
        expenses = expenses.order_by('status')
    elif sort == 'status_desc':
        expenses = expenses.order_by('-status')
    else:
        expenses = expenses.order_by('-date', '-created_at')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="expenses_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Category', 'Description', 'Vendor/Employee', 'Amount', 'Status', 'Recorded By', 'Paid Status', 'Product Link', 'Product Details', 'Order Details'])
    
    product_ids = [e.payload.get('product_id') for e in expenses if e.payload and e.payload.get('product_id')]
    order_ids = [e.payload.get('order_id') for e in expenses if e.payload and e.payload.get('order_id')]
    
    from tracker.models import Product, Order
    products = {str(p.id): p for p in Product.objects.filter(id__in=product_ids)}
    orders = {str(o.id): o for o in Order.objects.filter(id__in=order_ids)}

    for e in expenses:
        product_link = ''
        product_detail = ''
        order_detail = ''
        
        if e.payload:
            prod_id = e.payload.get('product_id')
            if prod_id:
                try:
                    path = reverse('tracker:product_detail', args=[prod_id])
                    product_link = request.build_absolute_uri(path)
                except Exception:
                    pass
                if prod_id in products:
                    product_detail = products[prod_id].item_name
                    
            ord_id = e.payload.get('order_id')
            if ord_id and ord_id in orders:
                order_detail = f"{orders[ord_id].order_number} ({orders[ord_id].customer_name})"

        writer.writerow([
            e.date.strftime('%d-%b-%Y') if e.date else '',
            e.expense_type,
            e.title,
            e.employee_code or '',
            e.amount,
            e.status,
            e.submitted_by.username if e.submitted_by else '',
            'Paid' if e.is_paid else 'Unpaid',
            product_link,
            product_detail,
            order_detail
        ])
        
    return response