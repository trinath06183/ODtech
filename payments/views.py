from core.decorators import require_permission
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.db.models import Sum, Q
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from contacts.models import Contact
from config.models import CompanyProfile
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import Payment


@require_permission('PAYMENTS', 'read')
def payment_list(request):
    page_num = request.GET.get('page', 1)
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    q = request.GET.get('q', '').strip()
    payment_mode = request.GET.get('payment_mode', '').strip()
    sort_by = request.GET.get('sort_by', '-date').strip()
    
    payments = Payment.objects.select_related('contact')
    
    from django.db.models import Q
    if q:
        payments = payments.filter(
            Q(contact__name__icontains=q) |
            Q(document_ref__icontains=q) |
            Q(reference_number__icontains=q)
        )
        
    if payment_mode:
        payments = payments.filter(payment_mode=payment_mode)
        
    if start_date:
        payments = payments.filter(date__gte=start_date)
    if end_date:
        payments = payments.filter(date__lte=end_date)
        
    # Validation and applying sort_by
    allowed_sort_fields = ['date', '-date', 'amount', '-amount', 'contact__name', '-contact__name', 'payment_mode', '-payment_mode']
    if sort_by not in allowed_sort_fields:
        sort_by = '-date'
    
    if sort_by == '-date':
        payments = payments.order_by('-date', '-id')
    elif sort_by == 'date':
        payments = payments.order_by('date', 'id')
    else:
        payments = payments.order_by(sort_by, '-id')
        
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
        'next_page': page_obj.next_page_number() if page_obj.has_next() else None,
        'q': q,
        'start_date': start_date,
        'end_date': end_date,
        'payment_mode': payment_mode,
        'sort_by': sort_by,
        'payment_modes': Payment.PAYMENT_MODES,
    })


@require_permission('PAYMENTS', 'write')
def payment_create(request):
    contacts  = Contact.objects.all().order_by('name')
    from documents.models import Document
    documents = Document.objects.all().order_by('-date', '-id')

    # Pre-select contact and document if passed as query param
    preselect_contact = request.GET.get('contact', '')
    preselect_document = request.GET.get('document', '')

    if request.method == 'POST':
        contact_id = request.POST.get('contact')
        document_ref = request.POST.get('document_ref', '').strip() or None
        amount = request.POST.get('amount', '').strip()
        payment_mode = request.POST.get('payment_mode', 'Cash')
        payment_date = request.POST.get('date', '').strip() or None
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
            payment = Payment.objects.create(
                contact_id=contact_id,
                document_ref=document_ref,
                amount=amount,
                payment_mode=payment_mode,
                reference_number=reference_number,
                notes=notes,
            )
            if payment_date:
                try:
                    Payment.objects.filter(id=payment.id).update(date=payment_date)
                except Exception:
                    pass
            messages.success(request, 'Payment recorded successfully.')
            next_url = request.GET.get('next') or request.POST.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('payment_list')

    from django.utils import timezone
    return render(request, 'payments/payment_form.html', {
        'contacts': contacts,
        'documents': documents,
        'payment_modes': Payment.PAYMENT_MODES,
        'preselect_contact': preselect_contact,
        'preselect_document': preselect_document,
        'today': timezone.localdate(),
        'is_edit': False,
    })


@require_permission('PAYMENTS', 'write')
def payment_edit(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    contacts = Contact.objects.all().order_by('name')
    from documents.models import Document
    documents = Document.objects.all().order_by('-date', '-id')

    if request.method == 'POST':
        contact_id = request.POST.get('contact')
        document_ref = request.POST.get('document_ref', '').strip() or None
        amount = request.POST.get('amount', '').strip()
        payment_mode = request.POST.get('payment_mode', 'Cash')
        payment_date = request.POST.get('date', '').strip() or None
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
            payment.contact_id = contact_id
            payment.document_ref = document_ref
            payment.amount = amount
            payment.payment_mode = payment_mode
            payment.reference_number = reference_number
            payment.notes = notes
            payment.save()
            if payment_date:
                try:
                    Payment.objects.filter(id=payment.id).update(date=payment_date)
                except Exception:
                    pass
            messages.success(request, 'Payment updated successfully.')
            next_url = request.GET.get('next') or request.POST.get('next')
            if next_url:
                return redirect(next_url)
            return redirect('payment_list')

    # Find linked doc id for preselection if available
    linked_doc = payment.linked_document
    preselect_document = str(linked_doc.id) if linked_doc else ''

    from django.utils import timezone
    return render(request, 'payments/payment_form.html', {
        'payment': payment,
        'contacts': contacts,
        'documents': documents,
        'payment_modes': Payment.PAYMENT_MODES,
        'preselect_contact': str(payment.contact_id),
        'preselect_document': preselect_document,
        'today': timezone.localdate(),
        'is_edit': True,
    })


@require_permission('PAYMENTS', 'write')
def payment_delete(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    if request.method == 'POST':
        action_type = request.POST.get('action_type', 'delete')
        if action_type == 'delink':
            doc_ref = payment.document_ref
            payment.document_ref = None
            payment.save()
            messages.success(request, f'Payment of ₹{payment.amount:,.2f} delinked from document {doc_ref or ""}. Payment record remains saved in ledger.')
        else:
            payment.delete()
            messages.success(request, 'Payment record permanently deleted.')
    next_url = request.GET.get('next') or request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('payment_list')

# ==============================================================================
# EXPENSE MANAGEMENT VIEWS
# ==============================================================================
from django.utils import timezone
from .models import Expense, user_can_view_fixed_costs
from .forms import ExpenseForm

def get_user_expense_q(user):
    """
    Returns Q filter matching expenses that belong to `user`.
    An expense belongs to `user` if:
    1. employee_code matches user's empid or username.
    2. OR employee_code is unassigned (empty/null) and user was the submitter.
    If employee_code is explicitly set to someone else (e.g. EMP002), it belongs
    to that employee, not the administrator who recorded it.
    """
    user_empid = getattr(user, 'empid', None)
    username = getattr(user, 'username', '')

    codes = []
    if user_empid and user_empid.strip():
        codes.append(user_empid.strip())
    if username and username.strip():
        codes.append(username.strip())

    code_q = Q()
    for c in codes:
        code_q |= Q(employee_code__iexact=c)

    unassigned_self_q = Q(submitted_by=user) & (Q(employee_code__isnull=True) | Q(employee_code=''))
    return code_q | unassigned_self_q

@require_permission('PAYMENTS', 'read')
def expense_list(request):
    can_view_fc = user_can_view_fixed_costs(request.user)
    current_tab = request.GET.get('tab', 'all').strip().lower()
    if current_tab == 'confidential' and not can_view_fc:
        current_tab = 'all'
    elif current_tab not in ('my', 'confidential'):
        current_tab = 'all'

    my_q = get_user_expense_q(request.user)
    fc_q = Expense.get_fixed_cost_q()

    # General / All Expenses strictly excludes confidential expenses
    general_qs = Expense.objects.exclude(fc_q)
    confidential_qs = Expense.objects.filter(fc_q) if can_view_fc else Expense.objects.none()

    all_count = general_qs.count()
    my_count = general_qs.filter(my_q).count()
    confidential_count = confidential_qs.count()

    if current_tab == 'confidential':
        expenses = confidential_qs
    elif current_tab == 'my':
        expenses = general_qs.filter(my_q)
    else:
        expenses = general_qs

    search = request.GET.get('search', '').strip()
    category = request.GET.get('category', '').strip()
    status = request.GET.get('status', '').strip()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    employee_code = request.GET.get('employee_code', '').strip()
    sort = request.GET.get('sort', '').strip()

    if search:
        import re
        search_q = (
            Q(title__icontains=search) | 
            Q(notes__icontains=search) |
            Q(employee_code__icontains=search) |
            Q(submitted_by__empid__icontains=search) |
            Q(submitted_by__username__icontains=search) |
            Q(submitted_by__first_name__icontains=search) |
            Q(submitted_by__last_name__icontains=search) |
            Q(expense_type__icontains=search)
        )
        # Check if search is an expense ID like e-0000023, e-23, or a raw number
        clean_id = re.sub(r'^[eE]-?0*', '', search)
        if clean_id.isdigit():
            search_q |= Q(id=int(clean_id))
        expenses = expenses.filter(search_q)
    if category:
        expenses = expenses.filter(expense_type=category)
    if status:
        expenses = expenses.filter(status=status)
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

    calc_expenses = expenses.filter(status='Approved')
    total_expenses = calc_expenses.aggregate(total=Sum('amount'))['total'] or 0
    total_paid = calc_expenses.filter(is_paid=True).aggregate(total=Sum('amount'))['total'] or 0
    total_unpaid = calc_expenses.filter(is_paid=False).aggregate(total=Sum('amount'))['total'] or 0

    page_num = request.GET.get('page', 1)
    total_count = expenses.count()
    paginator = Paginator(expenses, 30)
    page_obj = paginator.get_page(page_num)

    User = get_user_model()
    all_users = list(User.objects.all())
    user_by_empid = {u.empid.strip().upper(): u for u in all_users if u.empid}
    user_by_username = {u.username.strip().lower(): u for u in all_users if u.username}

    for exp in page_obj:
        code = (exp.employee_code or '').strip()
        matched = user_by_empid.get(code.upper()) or user_by_username.get(code.lower())
        if matched:
            exp._cached_employee_user = matched
            exp._cached_employee_name = matched.get_full_name().strip() or matched.first_name or matched.username
        else:
            exp._cached_employee_user = exp.submitted_by
            exp._cached_employee_name = (exp.submitted_by.get_full_name().strip() or exp.submitted_by.first_name) if exp.submitted_by else ''

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

    category_choices = [('Fixed Cost', Expense.FIXED_COSTS)] if current_tab == 'confidential' else [('Daily Expenses', Expense.DAILY_EXPENSES)]

    return render(request, 'payments/expense_list.html', {
        'expenses': page_obj,
        'expense_types': category_choices,
        'can_view_fixed_costs': can_view_fc,
        'total_expenses': total_expenses,
        'total_paid': total_paid,
        'total_unpaid': total_unpaid,
        'total_count': total_count,
        'all_count': all_count,
        'my_count': my_count,
        'confidential_count': confidential_count,
        'current_tab': current_tab,
        'has_next': page_obj.has_next(),
        'next_page': page_obj.next_page_number() if page_obj.has_next() else '',
    })

@require_permission('PAYMENTS', 'read')
def print_unpaid_expenses(request):
    can_view_fc = user_can_view_fixed_costs(request.user)
    tab = request.GET.get('tab', 'all').strip().lower()
    unpaid_expenses = Expense.objects.exclude(status='Pending').exclude(status='Rejected').filter(is_paid=False)
    
    if tab == 'confidential':
        if can_view_fc:
            unpaid_expenses = unpaid_expenses.filter(Expense.get_fixed_cost_q())
        else:
            unpaid_expenses = unpaid_expenses.none()
    elif tab == 'my':
        unpaid_expenses = unpaid_expenses.exclude(Expense.get_fixed_cost_q()).filter(get_user_expense_q(request.user))
    else:
        unpaid_expenses = unpaid_expenses.exclude(Expense.get_fixed_cost_q())

    unpaid_expenses = unpaid_expenses.select_related('submitted_by').order_by('employee_code', 'date')
    total_unpaid = unpaid_expenses.aggregate(total=Sum('amount'))['total'] or 0

    from collections import defaultdict
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # Pre-map all users by empid, username, and full name
    all_users = list(User.objects.all())
    user_by_empid = {u.empid.strip().upper(): u for u in all_users if u.empid}
    user_by_username = {u.username.strip().lower(): u for u in all_users if u.username}

    grouped_dict = defaultdict(list)
    for exp in unpaid_expenses:
        # Determine canonical employee code
        emp_code = (exp.employee_code or '').strip()
        if not emp_code and exp.submitted_by:
            emp_code = (exp.submitted_by.empid or exp.submitted_by.username or 'Unassigned').strip()

        # If code is a username that has an empid, map to the empid for consolidation
        if emp_code.lower() in user_by_username and user_by_username[emp_code.lower()].empid:
            emp_code = user_by_username[emp_code.lower()].empid

        if not emp_code:
            emp_code = 'Unassigned'

        grouped_dict[emp_code].append(exp)

    grouped_expenses = []
    for emp_code, exp_list in grouped_dict.items():
        emp_total = sum(e.amount for e in exp_list)
        
        # Look up employee full name by the assigned employee code / empid first
        matched_user = user_by_empid.get(emp_code.upper()) or user_by_username.get(emp_code.lower())
        
        if matched_user:
            full_name = matched_user.get_full_name().strip() or matched_user.first_name or matched_user.username
        else:
            first_user = exp_list[0].submitted_by if exp_list else None
            full_name = (first_user.get_full_name().strip() or first_user.first_name or '') if first_user else ''

        grouped_expenses.append({
            'employee_code': emp_code,
            'employee_name': full_name,
            'expenses': exp_list,
            'subtotal': emp_total,
            'count': len(exp_list),
        })

    return render(request, 'payments/print_unpaid_expenses.html', {
        'grouped_expenses': grouped_expenses,
        'total_unpaid': total_unpaid,
        'total_count': unpaid_expenses.count(),
        'company': CompanyProfile.objects.first(),
    })

@require_permission('PAYMENTS', 'write')
def expense_bulk_create(request):
    """Allow Admin or Superuser to enter and submit multiple expenses at once."""
    is_admin = request.user.is_superuser or request.user.is_staff or getattr(request.user, 'role', '') in ['Admin', 'Managing Director', 'Director']
    if not is_admin:
        messages.error(request, 'Permission denied. Submitting multiple expenses at once is only available for Administrators and Superusers.')
        return redirect('expense_list')

    import datetime
    import json
    from decimal import Decimal
    from django.db import transaction

    can_view_fc = user_can_view_fixed_costs(request.user)
    daily_categories = [c[0] for c in Expense.DAILY_EXPENSES]
    fixed_categories = [c[0] for c in Expense.FIXED_COSTS] if can_view_fc else []
    default_emp_code = (getattr(request.user, 'empid', None) or '').strip()
    today_iso = datetime.date.today().isoformat()

    User = get_user_model()
    active_employees = [
        {
            'code': (u.empid or u.username).strip(),
            'name': u.get_full_name().strip() or u.first_name or u.username,
        }
        for u in User.objects.filter(is_active=True).order_by('first_name', 'last_name')
    ]

    if request.method == 'POST':
        global_emp_code = request.POST.get('global_employee_code', '').strip()
        if global_emp_code.upper() in ['OFFICE', 'OFFICIAL', 'COMPANY', 'OFF']:
            global_emp_code = 'OFFICE'
        elif not global_emp_code:
            global_emp_code = default_emp_code

        # Parse row indices
        row_indices_raw = request.POST.getlist('row_indices')
        indices = []
        for val in row_indices_raw:
            for item in str(val).split(','):
                item = item.strip()
                if item and item not in indices:
                    indices.append(item)

        # Fallback: discover row IDs from POST parameters
        if not indices:
            for k in request.POST.keys():
                if k.startswith('title_'):
                    idx = k.replace('title_', '').strip()
                    if idx and idx not in indices:
                        indices.append(idx)

        valid_items = []
        errors = []
        row_states = []

        for idx in indices:
            date_str = request.POST.get(f'date_{idx}', '').strip()
            title = request.POST.get(f'title_{idx}', '').strip()
            expense_type = request.POST.get(f'expense_type_{idx}', '').strip()
            custom_category = request.POST.get(f'custom_category_{idx}', '').strip()
            amount_str = request.POST.get(f'amount_{idx}', '').strip()
            gst_amount_str = request.POST.get(f'gst_amount_{idx}', '0').strip() or '0'
            raw_emp = request.POST.get(f'employee_code_{idx}', '').strip()
            if not raw_emp:
                emp_code = global_emp_code
            elif raw_emp.upper() in ['OFFICE', 'OFFICIAL', 'COMPANY', 'OFF']:
                emp_code = 'OFFICE'
            else:
                emp_code = raw_emp
            notes = request.POST.get(f'notes_{idx}', '').strip()
            is_conf = bool(request.POST.get(f'is_confidential_{idx}'))
            receipt = request.FILES.get(f'receipt_{idx}')

            row_state = {
                'id': idx,
                'date': date_str or today_iso,
                'title': title,
                'expense_type': expense_type,
                'custom_category': custom_category,
                'amount': amount_str,
                'gst_amount': gst_amount_str,
                'employee_code': emp_code,
                'notes': notes,
                'is_confidential': is_conf,
            }
            row_states.append(row_state)

            # Skip row if totally empty
            if not title and not amount_str and not expense_type:
                continue

            row_num = len(row_states)
            row_has_error = False

            if not title:
                errors.append(f"Row #{row_num}: Title / Purpose is required.")
                row_has_error = True

            final_category = expense_type
            if not final_category:
                errors.append(f"Row #{row_num}: Category is required.")
                row_has_error = True
            elif final_category == '__custom__':
                if not custom_category:
                    errors.append(f"Row #{row_num}: Please enter the custom category name.")
                    row_has_error = True
                else:
                    final_category = custom_category

            if final_category and Expense.is_fixed_cost_category(final_category) and not can_view_fc:
                errors.append(f"Row #{row_num}: You do not have permission to submit confidential / fixed cost expenses.")
                row_has_error = True

            parsed_date = None
            if not date_str:
                errors.append(f"Row #{row_num}: Date is required.")
                row_has_error = True
            else:
                try:
                    parsed_date = datetime.date.fromisoformat(date_str)
                except ValueError:
                    errors.append(f"Row #{row_num}: Invalid date '{date_str}'. Expected format YYYY-MM-DD.")
                    row_has_error = True

            parsed_amount = None
            if not amount_str:
                errors.append(f"Row #{row_num}: Amount is required.")
                row_has_error = True
            else:
                try:
                    parsed_amount = Decimal(amount_str)
                    if parsed_amount <= 0:
                        errors.append(f"Row #{row_num}: Amount must be greater than zero.")
                        row_has_error = True
                except Exception:
                    errors.append(f"Row #{row_num}: Invalid amount '{amount_str}'.")
                    row_has_error = True

            parsed_gst = Decimal('0.00')
            if gst_amount_str:
                try:
                    parsed_gst = Decimal(gst_amount_str)
                    if parsed_gst < 0:
                        errors.append(f"Row #{row_num}: GST Amount cannot be negative.")
                        row_has_error = True
                except Exception:
                    errors.append(f"Row #{row_num}: Invalid GST amount '{gst_amount_str}'.")
                    row_has_error = True

            if not row_has_error:
                valid_items.append({
                    'title': title,
                    'expense_type': final_category,
                    'date': parsed_date,
                    'amount': parsed_amount,
                    'gst_amount': parsed_gst,
                    'employee_code': emp_code or 'OFFICE',
                    'notes': notes,
                    'is_confidential': is_conf or Expense.is_fixed_cost_category(final_category),
                    'receipt': receipt,
                })

        if not valid_items and not errors:
            errors.append("Please fill in at least one expense row.")

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, 'payments/expense_bulk_form.html', {
                'title': 'Submit Multiple Expenses',
                'can_view_fc': can_view_fc,
                'daily_categories': daily_categories,
                'fixed_categories': fixed_categories,
                'global_employee_code': global_emp_code,
                'initial_rows_json': json.dumps(row_states if row_states else []),
                'default_date': today_iso,
                'active_employees': active_employees,
            })

        # Atomic bulk create
        total_amount = Decimal('0.00')
        with transaction.atomic():
            for item in valid_items:
                exp = Expense.objects.create(
                    title=item['title'],
                    expense_type=item['expense_type'],
                    date=item['date'],
                    amount=item['amount'],
                    gst_amount=item['gst_amount'],
                    employee_code=item['employee_code'],
                    submitted_by=request.user,
                    status='Pending',
                    notes=item['notes'],
                    is_confidential=item['is_confidential'],
                    receipt=item['receipt'],
                )
                total_amount += item['amount']

        messages.success(request, f"Successfully submitted {len(valid_items)} expenses totaling ₹{total_amount:,.2f}.")
        return redirect('expense_list')

    # Default GET initial rows (start with 3 clean rows)
    import json
    default_rows = [
        {'id': '0', 'date': today_iso, 'title': '', 'expense_type': '', 'custom_category': '', 'amount': '', 'gst_amount': '0.00', 'employee_code': default_emp_code, 'notes': '', 'is_confidential': False},
        {'id': '1', 'date': today_iso, 'title': '', 'expense_type': '', 'custom_category': '', 'amount': '', 'gst_amount': '0.00', 'employee_code': default_emp_code, 'notes': '', 'is_confidential': False},
        {'id': '2', 'date': today_iso, 'title': '', 'expense_type': '', 'custom_category': '', 'amount': '', 'gst_amount': '0.00', 'employee_code': default_emp_code, 'notes': '', 'is_confidential': False},
    ]

    return render(request, 'payments/expense_bulk_form.html', {
        'title': 'Submit Multiple Expenses',
        'can_view_fc': can_view_fc,
        'daily_categories': daily_categories,
        'fixed_categories': fixed_categories,
        'global_employee_code': default_emp_code,
        'initial_rows_json': json.dumps(default_rows),
        'default_date': today_iso,
        'active_employees': active_employees,
    })


@require_permission('PAYMENTS', 'write')
def expense_create(request):
    User = get_user_model()
    active_employees = [
        {
            'code': (u.empid or u.username).strip(),
            'name': u.get_full_name().strip() or u.first_name or u.username,
        }
        for u in User.objects.filter(is_active=True).order_by('first_name', 'last_name')
    ]

    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.submitted_by = request.user
            raw_code = request.POST.get('employee_code', '').strip()
            if raw_code.upper() in ['OFFICE', 'OFFICIAL', 'COMPANY', 'OFF'] or expense.employee_code == 'OFFICE':
                expense.employee_code = 'OFFICE'
            elif not expense.employee_code and request.user.empid:
                expense.employee_code = request.user.empid
            
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
        form = ExpenseForm(user=request.user)
    return render(request, 'payments/expense_form.html', {
        'form': form,
        'title': 'Submit New Expense',
        'active_employees': active_employees,
    })

@require_permission('PAYMENTS', 'write')
def expense_edit(request, pk):
    is_admin = request.user.is_superuser or request.user.is_staff or getattr(request.user, 'role', '') in ['Admin', 'Managing Director', 'Director']
    if is_admin:
        expense = get_object_or_404(Expense, pk=pk)
    else:
        expense = get_object_or_404(Expense, pk=pk, submitted_by=request.user)

    if expense.is_fixed_cost and not user_can_view_fixed_costs(request.user):
        messages.error(request, 'Permission denied. You do not have permission to view or edit Fixed Cost expenses.')
        return redirect('expense_list')

    # Non-admin users require explicit admin permission to edit an expense
    if not is_admin and expense.edit_permission_status != 'APPROVED':
        return render(request, 'payments/expense_edit_permission.html', {
            'expense': expense,
            'title': 'Admin Permission Required',
        })

    allowed_statuses = ['Pending', 'Clarification', 'Clarification Provided']
    if expense.status not in allowed_statuses and not is_admin and expense.edit_permission_status != 'APPROVED':
        messages.error(request, 'You cannot edit an expense that has already been approved or rejected.')
        return redirect('expense_list')

    if request.method == 'POST':
        form = ExpenseForm(request.POST, request.FILES, instance=expense, user=request.user)
        if form.is_valid():
            expense = form.save(commit=False)

            # Once saved by non-admin, consume the one-time edit permission
            if not is_admin:
                expense.edit_permission_status = 'NONE'

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

            # Handle clarification response
            clarification_resp = request.POST.get('clarification_response', '').strip()
            was_in_clarification = (expense.status == 'Clarification') or bool(clarification_resp)
            if clarification_resp:
                expense.clarification_response = clarification_resp
            if was_in_clarification:
                expense.status = 'Clarification Provided'
                expense.clarification_popup_seen = True

            expense.save()

            if was_in_clarification and clarification_resp:
                from .services import ExpenseNotificationService
                ExpenseNotificationService.notify_clarification_submitted(expense, request.user, request=request)
                messages.success(request, 'Clarification and updated expense submitted successfully. Admin has been notified.')
            else:
                messages.success(request, 'Expense updated successfully.')

            return redirect('expense_list')
    else:
        form = ExpenseForm(instance=expense, user=request.user)
    
    User = get_user_model()
    active_employees = [
        {
            'code': (u.empid or u.username).strip(),
            'name': u.get_full_name().strip() or u.first_name or u.username,
        }
        for u in User.objects.filter(is_active=True).order_by('first_name', 'last_name')
    ]
    return render(request, 'payments/expense_form.html', {
        'form': form,
        'title': 'Edit Expense',
        'expense': expense,
        'is_edit_approved': (expense.edit_permission_status == 'APPROVED'),
        'active_employees': active_employees,
    })


@require_permission('PAYMENTS', 'write')
@require_POST
def expense_ask_edit_permission(request, pk):
    is_admin = request.user.is_superuser or request.user.is_staff or getattr(request.user, 'role', '') in ['Admin', 'Managing Director', 'Director']
    if is_admin:
        messages.info(request, "Administrators can edit expenses directly without asking for permission.")
        return redirect('expense_edit', pk=pk)

    expense = get_object_or_404(Expense, pk=pk, submitted_by=request.user)
    reason = request.POST.get('reason', '').strip()

    expense.edit_permission_status = 'PENDING'
    expense.edit_requested_by = request.user
    expense.edit_requested_at = timezone.now()
    expense.edit_request_reason = reason
    expense.save(update_fields=['edit_permission_status', 'edit_requested_by', 'edit_requested_at', 'edit_request_reason'])

    from .services import ExpenseNotificationService
    ExpenseNotificationService.notify_edit_permission_requested(expense, request.user, reason=reason, request=request)

    messages.success(request, 'Permission request sent to Admin. You will receive a notification once reviewed.')
    return redirect('expense_edit', pk=pk)


@require_permission('PAYMENTS', 'write')
@require_POST
def expense_decide_edit_permission(request, pk, decision):
    is_admin = request.user.is_superuser or request.user.is_staff or getattr(request.user, 'role', '') in ['Admin', 'Managing Director', 'Director']
    if not is_admin:
        messages.error(request, 'Permission denied. Only Administrators can review edit requests.')
        return redirect('expense_detail', pk=pk)

    expense = get_object_or_404(Expense, pk=pk)
    decision = decision.upper()

    from .services import ExpenseNotificationService

    if decision == 'APPROVE':
        expense.edit_permission_status = 'APPROVED'
        expense.edit_reviewed_by = request.user
        expense.edit_reviewed_at = timezone.now()
        expense.save(update_fields=['edit_permission_status', 'edit_reviewed_by', 'edit_reviewed_at'])

        ExpenseNotificationService.notify_edit_permission_decided(expense, 'APPROVED', request.user, request=request)
        user_name = expense.edit_requested_by.get_full_name() or expense.edit_requested_by.username if expense.edit_requested_by else "User"
        messages.success(request, f"Edit permission APPROVED for {user_name}. They can now edit this expense.")

    elif decision == 'REJECT':
        expense.edit_permission_status = 'REJECTED'
        expense.edit_reviewed_by = request.user
        expense.edit_reviewed_at = timezone.now()
        expense.save(update_fields=['edit_permission_status', 'edit_reviewed_by', 'edit_reviewed_at'])

        ExpenseNotificationService.notify_edit_permission_decided(expense, 'REJECTED', request.user, request=request)
        user_name = expense.edit_requested_by.get_full_name() or expense.edit_requested_by.username if expense.edit_requested_by else "User"
        messages.info(request, f"Edit permission REJECTED for {user_name}.")

    return redirect('expense_detail', pk=pk)

@require_permission('PAYMENTS', 'write')
def expense_raise_clarification(request, pk):
    is_admin = request.user.is_superuser or request.user.is_staff or getattr(request.user, 'role', '') in ['Admin', 'Managing Director', 'Director']
    if not is_admin:
        messages.error(request, 'Permission denied. Only Administrators can raise clarification.')
        return redirect('expense_list')

    expense = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        query = request.POST.get('clarification_query', '').strip()
        if not query:
            messages.error(request, 'Please enter the clarification request details.')
            referer = request.META.get('HTTP_REFERER')
            return redirect(referer) if referer else redirect('expense_list')

        expense.status = 'Clarification'
        expense.clarification_query = query
        expense.clarification_raised_by = request.user
        expense.clarification_raised_at = timezone.now()
        expense.clarification_popup_seen = False
        expense.save()

        from .services import ExpenseNotificationService
        ExpenseNotificationService.notify_clarification_raised(expense, request.user, request=request)

        messages.success(request, f'Clarification raised for {expense.expense_id}. Submitter has been notified by registered email and login alert.')

    referer = request.META.get('HTTP_REFERER')
    return redirect(referer) if referer else redirect('expense_list')

@require_permission('PAYMENTS', 'read')
def dismiss_clarification_popup(request):
    if request.method == 'POST' and request.user.is_authenticated:
        user_code = getattr(request.user, 'empid', None) or ''
        q_filter = Q(submitted_by=request.user)
        if user_code:
            q_filter |= Q(employee_code__iexact=user_code)
        Expense.objects.filter(q_filter, status='Clarification', clarification_popup_seen=False).update(clarification_popup_seen=True)
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'ignored'}, status=400)

@require_permission('PAYMENTS', 'read')
def expense_detail(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if expense.is_fixed_cost and not user_can_view_fixed_costs(request.user):
        messages.error(request, 'Permission denied. You do not have permission to view Fixed Cost expenses.')
    is_admin = request.user.is_superuser or request.user.is_staff or getattr(request.user, 'role', '') in ['Admin', 'Managing Director', 'Director']
    return render(request, 'payments/expense_detail.html', {
        'title': 'View Expense',
        'expense': expense,
        'is_admin': is_admin,
    })

@require_permission('PAYMENTS', 'write')
def expense_delete(request, pk):
    is_admin = request.user.is_superuser or request.user.is_staff or getattr(request.user, 'role', '') in ['Admin', 'Managing Director', 'Director']
    if is_admin:
        expense = get_object_or_404(Expense, pk=pk)
    else:
        expense = get_object_or_404(Expense, pk=pk, submitted_by=request.user)

    if expense.is_fixed_cost and not user_can_view_fixed_costs(request.user):
        messages.error(request, 'Permission denied. You do not have permission to delete Fixed Cost expenses.')
        return redirect('expense_list')
        
    if not is_admin and expense.status not in ['Pending', 'Clarification', 'Clarification Provided']:
        messages.error(request, 'You can only delete pending or unapproved expenses.')
        return redirect('expense_list')
        
    if request.method == 'POST':
        expense.delete()
        messages.success(request, 'Expense deleted.')
    referer = request.META.get('HTTP_REFERER')
    return redirect(referer) if referer else redirect('expense_list')

@require_permission('PAYMENTS', 'write')
def expense_mark_paid(request, pk):
    expense = get_object_or_404(Expense, pk=pk, status='Approved', is_paid=False)
    if expense.is_fixed_cost and not user_can_view_fixed_costs(request.user):
        messages.error(request, 'Permission denied. You do not have permission to modify confidential expenses.')
        return redirect('expense_list')
    # Superusers, staff (admins), and the expense submitter can mark as paid
    is_admin = request.user.is_superuser or request.user.is_staff or getattr(request.user, 'role', '') in ['Admin', 'Managing Director', 'Director']
    if not is_admin and expense.submitted_by != request.user:
        messages.error(request, 'You do not have permission to perform this action.')
        return redirect('expense_list')
        
    if request.method == 'POST':
        expense.is_paid = True
        expense.paid_at = timezone.now()
        expense.save()
        messages.success(request, 'Expense marked as Paid.')
    referer = request.META.get('HTTP_REFERER')
    return redirect(referer) if referer else redirect('expense_list')

@require_permission('PAYMENTS', 'write')
def expense_approve(request, pk, status):
    is_admin = request.user.is_superuser or request.user.is_staff or getattr(request.user, 'role', '') in ['Admin', 'Managing Director', 'Director']
    if not is_admin:
        messages.error(request, 'Permission denied. Only Administrators can approve/reject expenses.')
        return redirect('expense_list')

    expense = get_object_or_404(Expense, pk=pk)
    if expense.is_fixed_cost and not user_can_view_fixed_costs(request.user):
        messages.error(request, 'Permission denied. You do not have permission to modify confidential expenses.')
        return redirect('expense_list')
    if status in ['Approved', 'Rejected']:
        expense.status = status
        expense.approved_by = request.user
        expense.approved_at = timezone.now()
        expense.save()

        if status == 'Approved':
            from .services import ExpenseNotificationService
            ExpenseNotificationService.notify_expense_approved(expense, request.user, request=request)

        messages.success(request, f'Expense {status.lower()} successfully.')
    referer = request.META.get('HTTP_REFERER')
    return redirect(referer) if referer else redirect('expense_list')

@require_permission('PAYMENTS', 'write')
def bulk_expense_action(request):
    is_admin = request.user.is_superuser or request.user.is_staff or getattr(request.user, 'role', '') in ['Admin', 'Managing Director', 'Director']
    if not is_admin:
        messages.error(request, 'Permission denied.')
        return redirect('expense_list')

    if request.method != 'POST':
        return redirect('expense_list')

    action = request.POST.get('action')
    expense_ids = request.POST.getlist('selected_expenses')

    if not expense_ids:
        messages.warning(request, 'No expenses selected.')
        return redirect('expense_list')

    expenses = Expense.objects.filter(pk__in=expense_ids)
    if not user_can_view_fixed_costs(request.user):
        expenses = expenses.exclude(Expense.get_fixed_cost_q())

    if action == 'approve':
        eligible = expenses.filter(status__in=['Pending', 'Clarification Provided'])
        count = 0
        from .services import ExpenseNotificationService
        for exp in eligible:
            exp.status = 'Approved'
            exp.approved_by = request.user
            exp.approved_at = timezone.now()
            exp.save()
            ExpenseNotificationService.notify_expense_approved(exp, request.user, request=request)
            count += 1
        messages.success(request, f'✅ {count} expense(s) approved successfully.')

    elif action == 'reject':
        updated = expenses.filter(status__in=['Pending', 'Clarification', 'Clarification Provided']).update(
            status='Rejected',
            approved_by=request.user,
            approved_at=timezone.now(),
        )
        messages.success(request, f'❌ {updated} expense(s) rejected.')

    elif action == 'mark_paid':
        updated = expenses.filter(status='Approved', is_paid=False).update(
            is_paid=True,
            paid_at=timezone.now(),
        )
        messages.success(request, f'💰 {updated} expense(s) marked as Paid.')

    else:
        messages.error(request, 'Invalid bulk action.')

    return redirect('expense_list')

@require_permission('PAYMENTS', 'read')
def employee_code_autocomplete(request):
    query = request.GET.get('q', '').strip()
    User = get_user_model()
    results = []

    # Include OFFICE option if matching query or on initial load
    if not query or any(kw in query.lower() for kw in ['off', 'com', 'gen', 'adm']):
        results.append({'code': 'OFFICE', 'name': 'OFFICE — Office / Company Expense (No User)'})

    if query:
        users = User.objects.filter(
            Q(empid__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(username__icontains=query),
            is_active=True
        ).order_by('first_name', 'last_name')[:50]
    else:
        users = User.objects.filter(is_active=True).order_by('first_name', 'last_name')[:200]

    for u in users:
        code = (u.empid or u.username).strip()
        full_name = u.get_full_name().strip() or u.first_name or u.username
        results.append({'code': code, 'name': f"{code} — {full_name}"})

    return JsonResponse(results, safe=False)


import csv
from django.http import HttpResponse

@require_permission('PAYMENTS', 'read')
def payment_export_csv(request):
    """Export payments list to CSV."""
    from payments.models import Payment
    q = request.GET.get('q', '').strip()
    payment_mode = request.GET.get('payment_mode', '').strip()
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()

    payments = Payment.objects.select_related('contact').all().order_by('-date', '-id')

    if q:
        payments = payments.filter(
            Q(contact__name__icontains=q) |
            Q(document_ref__icontains=q) |
            Q(reference_number__icontains=q)
        )
    if payment_mode:
        payments = payments.filter(payment_mode=payment_mode)
    if start_date:
        payments = payments.filter(date__gte=start_date)
    if end_date:
        payments = payments.filter(date__lte=end_date)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="payments_export.csv"'

    writer = csv.writer(response)
    writer.writerow(['Date', 'Contact', 'Document Ref', 'Amount', 'Payment Mode', 'Reference No.', 'Notes'])

    for p in payments:
        writer.writerow([
            p.date.strftime('%d-%b-%Y') if p.date else '',
            p.contact.name if p.contact else '',
            p.document_ref or '',
            p.amount,
            p.payment_mode or '',
            p.reference_number or '',
            p.notes or '',
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
    
    can_view_fc = user_can_view_fixed_costs(request.user)
    expenses = Expense.objects.select_related('submitted_by').all()
    tab = request.GET.get('tab', 'all').strip().lower()
    
    if tab == 'confidential':
        if can_view_fc:
            expenses = expenses.filter(Expense.get_fixed_cost_q())
        else:
            expenses = expenses.none()
    elif tab == 'my':
        expenses = expenses.exclude(Expense.get_fixed_cost_q()).filter(get_user_expense_q(request.user))
    else:
        expenses = expenses.exclude(Expense.get_fixed_cost_q())
    
    if search:
        expenses = expenses.filter(
            Q(title__icontains=search) | 
            Q(notes__icontains=search) |
            Q(employee_code__icontains=search) |
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
    writer.writerow(['Expense ID', 'Date', 'Category', 'Description', 'Vendor/Employee', 'Amount', 'Status', 'Recorded By', 'Paid Status', 'Product Link', 'Product Details', 'Order Details'])
    
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
            e.expense_id,
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