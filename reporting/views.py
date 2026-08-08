from core.decorators import require_permission
import json

from django.shortcuts import render
from django.db.models import Sum, Q, Count, Value, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal

from core.decorators import login_required, role_required, require_permission
from inventory.models import Product
from documents.models import Document
from payments.models import Payment, Expense
from edms.models import EDMSDocument, EDMSDocumentCategory


@require_permission('REPORTING', 'write')
def gst_report(request):
    """GST Report — billing module has been migrated to EDMS."""
    return render(request, 'reporting/gst_report.html', {
        'rows': [],
        'total_taxable': 0,
        'total_cgst': 0,
        'total_sgst': 0,
        'total_igst': 0,
        'total_grand': 0,
        'fy_options': [],
        'selected_fy': '',
        'selected_month': '',
        'notice': 'Billing documents have been migrated to the EDMS module.',
    })


@require_permission('REPORTING', 'read')
def stock_summary(request):
    products = Product.objects.annotate(
        annotated_stock=Coalesce(
            Sum('stock_transactions__quantity'),
            Value(0),
            output_field=DecimalField()
        )
    ).order_by('name')
    
    rows = []
    total_value = 0
    for p in products:
        stock = p.annotated_stock
        value = float(stock) * float(p.purchase_price)
        rows.append({
            'product': p,
            'stock': stock,
            'value': value,
        })
        total_value += value

    return render(request, 'reporting/stock_summary.html', {
        'rows': rows,
        'total_value': total_value,
    })


@require_permission('REPORTING', 'read')
def financial_dashboard(request):
    """Financial & Operational Summary Dashboard with P&L, sales, purchases, expenses, orders & reminders."""
    today = date.today()

    # ── Date filter ────────────────────────────────────────────────────────────
    period = request.GET.get('period', 'this_month')

    if period == 'today':
        start_date = today
        end_date = today
        label = "Today"
    elif period == 'this_week':
        start_date = today - timedelta(days=today.weekday())
        end_date = today
        label = "This Week"
    elif period == 'this_month':
        start_date = today.replace(day=1)
        end_date = today
        label = "This Month"
    elif period == 'last_month':
        first_of_month = today.replace(day=1)
        end_date = first_of_month - timedelta(days=1)
        start_date = end_date.replace(day=1)
        label = "Last Month"
    elif period == 'this_quarter':
        q = (today.month - 1) // 3
        start_date = date(today.year, q * 3 + 1, 1)
        end_date = today
        label = "This Quarter"
    elif period == 'this_fy':
        fy_start_year = today.year if today.month >= 4 else today.year - 1
        start_date = date(fy_start_year, 4, 1)
        end_date = today
        label = f"FY {fy_start_year}-{str(fy_start_year + 1)[2:]}"
    elif period == 'this_year':
        start_date = date(today.year, 1, 1)
        end_date = today
        label = f"Year {today.year}"
    elif period == 'custom':
        try:
            start_date = date.fromisoformat(request.GET.get('start', ''))
            end_date = date.fromisoformat(request.GET.get('end', ''))
            label = f"{start_date.strftime('%d %b %Y')} – {end_date.strftime('%d %b %Y')}"
        except (ValueError, TypeError):
            start_date = today.replace(day=1)
            end_date = today
            label = "This Month"
    else:
        start_date = today.replace(day=1)
        end_date = today
        label = "This Month"

    # ── 1. SALES: Invoices generated (from Documents module) ─────────────────
    docs_qs = Document.objects.filter(
        status='Approved',
        date__gte=start_date,
        date__lte=end_date,
    )

    # Sales = Invoices only (INV type)
    sales_qs = docs_qs.filter(type='INV').order_by('-date').select_related('contact')
    total_sales = sales_qs.aggregate(t=Sum('grand_total'))['t'] or Decimal('0')
    total_sales_tax = sales_qs.aggregate(t=Sum('tax_total'))['t'] or Decimal('0')
    total_sales_subtotal = sales_qs.aggregate(t=Sum('subtotal'))['t'] or Decimal('0')
    sales_count = sales_qs.count()

    # PIs (Proforma Invoices) count & amount for the period
    pi_qs = Document.objects.filter(type='PRO', date__gte=start_date, date__lte=end_date)
    pi_count = pi_qs.count()
    pi_amount = pi_qs.aggregate(t=Sum('grand_total'))['t'] or Decimal('0')
    # Invoice detail list for collapsible
    sales_invoice_list = list(sales_qs.values(
        'id', 'number', 'grand_total', 'date', 'contact__name'
    )[:100])

    # Quotations (separate — not part of sales)
    qtn_qs = docs_qs.filter(type='QTN')
    total_quotations = qtn_qs.aggregate(t=Sum('grand_total'))['t'] or Decimal('0')
    quotations_count = qtn_qs.count()

    # Credit Notes / Debit Notes
    credit_notes = docs_qs.filter(type='CRN').aggregate(t=Sum('grand_total'))['t'] or Decimal('0')
    debit_notes = docs_qs.filter(type='DBN').aggregate(t=Sum('grand_total'))['t'] or Decimal('0')

    # ── 2. PURCHASES: Invoices entered in EDMS ───────────────────────────────
    total_purchases = Decimal('0')
    purchases_count = 0
    purchase_invoice_list = []
    invoice_category_id = ''
    try:
        from edms.models import EDMSDocumentCategory
        invoice_cat = EDMSDocumentCategory.objects.filter(name__icontains='invoice', is_active=True).first()
        if invoice_cat:
            invoice_category_id = invoice_cat.id

        edms_all_invoices = EDMSDocument.objects.filter(
            is_deleted=False,
            category=invoice_cat,
            invoice_date__gte=start_date,
            invoice_date__lte=end_date,
        )

        total_purchases = edms_all_invoices.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        purchases_count = edms_all_invoices.count()
        purchase_invoice_list = list(edms_all_invoices.values(
            'id', 'invoice_number', 'title', 'amount', 'issue_date', 'invoice_date', 'vendor__name'
        ).order_by('-invoice_date')[:100])
    except Exception:
        pass

    # ── Payments received vs given in period ─────────────────────────────────
    po_payments_total = Decimal('0')
    try:
        payments_qs = Payment.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
        )
        po_numbers = set(Document.objects.filter(type='PO').values_list('number', flat=True))
        total_received = Decimal('0')
        for p in payments_qs:
            if p.document_ref and p.document_ref in po_numbers:
                po_payments_total += p.amount
            else:
                total_received += p.amount
        total_payments_received = total_received
        payments_count = payments_qs.count()
    except Exception:
        total_payments_received = Decimal('0')
        payments_count = 0

    # ── 3. EXPENSES: All expense entries in period ───────────────────────────
    try:
        # All expenses (any status) for total
        expenses_qs = Expense.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
        ).order_by('-date')
        total_expenses = expenses_qs.aggregate(t=Sum('amount'))['t'] or Decimal('0')
        expenses_count = expenses_qs.count()
        total_payments_given = total_expenses + po_payments_total

        # Expense detail list for collapsible
        expense_detail_list = list(expenses_qs.values(
            'id', 'title', 'expense_type', 'amount', 'date', 'status', 'employee_code'
        )[:100])

        pending_expenses = Expense.objects.filter(status='Pending').aggregate(t=Sum('amount'))['t'] or Decimal('0')

        daily_expenses = expenses_qs.filter(
            expense_type__in=['Petrol and Diesel', 'Travel', 'Hotel', 'Food Expenses',
                              'Office stationary', 'Courier expenses', 'Transportation Payment',
                              'Marketing Expenses', 'Customer Delight', 'Other Daily']
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        fixed_expenses = expenses_qs.filter(
            expense_type__in=['Staff salary', 'OFC rent', 'Electricity bill', 'Internet Bill',
                              'Google workspace', 'Website and hosting cost', 'Other Fixed']
        ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    except Exception:
        total_expenses = Decimal('0')
        total_payments_given = Decimal('0')
        expenses_count = 0
        pending_expenses = Decimal('0')
        daily_expenses = Decimal('0')
        fixed_expenses = Decimal('0')
        expense_detail_list = []

    unpaid_po_advances = Decimal('0')
    try:
        approved_pos = Document.objects.filter(type='PO', status='Approved')
        po_numbers = list(approved_pos.values_list('number', flat=True))
        
        po_payments = Payment.objects.filter(document_ref__in=po_numbers).values('document_ref').annotate(total_paid=Sum('amount'))
        po_paid_dict = {item['document_ref']: item['total_paid'] or Decimal('0') for item in po_payments}
        
        for po in approved_pos:
            paid_amount = po_paid_dict.get(po.number, Decimal('0'))
            advance_required = po.grand_total * Decimal('0.3')
            remaining_advance = advance_required - paid_amount
            if remaining_advance > 0:
                unpaid_po_advances += remaining_advance
    except Exception:
        pass

    amount_needed_to_pay = pending_expenses + unpaid_po_advances

    # ── Order Tracker Metrics ──────────────────────────────────────────────────
    total_orders = 0
    order_open = 0
    order_in_progress = 0
    order_completed = 0
    order_other = 0
    try:
        from tracker.models import Order
        orders_qs = Order.objects.filter(
            created_at__gte=timezone.make_aware(timezone.datetime.combine(start_date, timezone.datetime.min.time())),
            created_at__lte=timezone.make_aware(timezone.datetime.combine(end_date, timezone.datetime.max.time())),
        )
        total_orders = orders_qs.count()
        order_open = orders_qs.filter(order_status='OPEN').count()
        order_in_progress = orders_qs.filter(order_status='IN_PROGRESS').count()
        order_completed = orders_qs.filter(order_status='CLOSED').count()
        order_other = max(0, total_orders - (order_open + order_in_progress + order_completed))
    except Exception:
        pass

    # ── Profit Calculations ───────────────────────────────────────────────────
    gross_profit = total_sales - total_purchases
    gross_margin_pct = (gross_profit / total_sales * 100) if total_sales else Decimal('0')

    net_profit = gross_profit - total_expenses + (debit_notes - credit_notes)
    net_margin_pct = (net_profit / total_sales * 100) if total_sales else Decimal('0')

    outstanding_receivables = max(Decimal('0'), total_sales - total_payments_received)

    # ── Payment Reminders & Urgent Alerts ──────────────────────────────────────
    reminders = []
    try:
        overdue_docs = Document.objects.filter(
            type='INV', status='Approved',
            date__lt=today - timedelta(days=30)
        ).select_related('contact').order_by('date')[:5]
        for doc in overdue_docs:
            reminders.append({
                'title': f"Overdue Invoice #{doc.number or doc.id}",
                'party': doc.contact.name if doc.contact else "Customer",
                'amount': doc.grand_total,
                'date': doc.date,
                'type': 'receivable',
                'is_urgent': True,
                'link': f"/documents/{doc.id}/preview/"
            })

        pending_exp_list = Expense.objects.filter(
            status='Pending'
        ).order_by('-date')[:5]
        for exp in pending_exp_list:
            reminders.append({
                'title': f"Pending Expense: {exp.expense_type}",
                'party': exp.paid_to or "Vendor",
                'amount': exp.amount,
                'date': exp.date,
                'type': 'payable',
                'is_urgent': False,
                'link': "/payments/expenses/"
            })
    except Exception:
        pass

    # ── Monthly / Yearly trend data (last 6 intervals) ─────────────────────────
    monthly_trend = []
    try:
        for i in range(5, -1, -1):
            ref = today.replace(day=1) - timedelta(days=i * 28)
            m_start = ref.replace(day=1)
            if m_start.month == 12:
                m_end = date(m_start.year + 1, 1, 1) - timedelta(days=1)
            else:
                m_end = date(m_start.year, m_start.month + 1, 1) - timedelta(days=1)

            m_sales = Document.objects.filter(
                type__in=['INV', 'PRO'], status='Approved',
                date__gte=m_start, date__lte=m_end
            ).aggregate(t=Sum('grand_total'))['t'] or Decimal('0')

            m_purchases = Document.objects.filter(
                type='PO', status='Approved',
                date__gte=m_start, date__lte=m_end
            ).aggregate(t=Sum('grand_total'))['t'] or Decimal('0')

            try:
                m_exp = Expense.objects.filter(
                    status='Approved', date__gte=m_start, date__lte=m_end
                ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
            except Exception:
                m_exp = Decimal('0')

            m_profit = m_sales - m_purchases - m_exp

            monthly_trend.append({
                'month': m_start.strftime('%b %Y'),
                'sales': float(m_sales),
                'purchases': float(m_purchases),
                'expenses': float(m_exp),
                'profit': float(m_profit),
            })
    except Exception:
        pass

    # ── Expense breakdown by category ─────────────────────────────────────────
    expense_by_type = []
    try:
        expense_by_type = list(
            Expense.objects.filter(date__gte=start_date, date__lte=end_date, status='Approved')
            .values('expense_type')
            .annotate(total=Sum('amount'), count=Count('id'))
            .order_by('-total')[:8]
        )
    except Exception:
        pass

    # ── Top customers by sales value ─────────────────────────────────────────
    top_customers = []
    try:
        top_customers = list(
            sales_qs.values('contact__name')
            .annotate(total=Sum('grand_total'), count=Count('id'))
            .order_by('-total')[:5]
        )
    except Exception:
        pass

    periods = [
        ('today', 'Today'),
        ('this_week', 'This Week'),
        ('this_month', 'This Month'),
        ('last_month', 'Last Month'),
        ('this_quarter', 'This Quarter'),
        ('this_fy', 'This FY'),
        ('this_year', 'This Year'),
    ]

    context = {
        # Period
        'period': period,
        'periods': periods,
        'label': label,
        'start_date': start_date,
        'end_date': end_date,
        # Sales & Purchases
        'total_sales': total_sales,
        'total_sales_subtotal': total_sales_subtotal,
        'total_sales_tax': total_sales_tax,
        'sales_count': sales_count,
        'sales_invoice_list': sales_invoice_list,
        'total_purchases': total_purchases,
        'purchases_count': purchases_count,
        'purchase_invoice_list': purchase_invoice_list,
        'invoice_category_id': invoice_category_id,
        'total_quotations': total_quotations,
        'quotations_count': quotations_count,
        # Payments & Payables
        'total_payments_received': total_payments_received,
        'payments_count': payments_count,
        'outstanding_receivables': outstanding_receivables,
        'total_payments_given': total_payments_given,
        'amount_needed_to_pay': amount_needed_to_pay,
        # Orders
        'total_orders': total_orders,
        'order_open': order_open,
        'order_in_progress': order_in_progress,
        'order_completed': order_completed,
        'order_other': order_other,
        # Proforma Invoices
        'pi_count': pi_count,
        'pi_amount': pi_amount,
        # Expenses
        'total_expenses': total_expenses,
        'daily_expenses': daily_expenses,
        'fixed_expenses': fixed_expenses,
        'expenses_count': expenses_count,
        'expense_detail_list': expense_detail_list,
        # Profit
        'gross_profit': gross_profit,
        'gross_margin_pct': gross_margin_pct,
        'net_profit': net_profit,
        'net_margin_pct': net_margin_pct,
        # Credit/Debit Notes
        'credit_notes': credit_notes,
        'debit_notes': debit_notes,
        # Reminders
        'reminders': reminders,
        'reminder_count': len(reminders),
        # Charts
        'monthly_trend': monthly_trend,
        'monthly_trend_json': json.dumps(monthly_trend),
        'expense_by_type': expense_by_type,
        'top_customers': top_customers,
    }

    return render(request, 'reporting/financial_dashboard.html', context)


@require_permission('REPORTING', 'read')
def business_planning_dashboard(request):

    from .models import PlannedOrder, PlannedPurchase
    from datetime import date
    from django.contrib import messages
    from django.shortcuts import redirect
    from django.db.models import Q, Sum
    from decimal import Decimal

    today = date.today()
    current_month_start = date(today.year, today.month, 1)
    
    if today.month == 1:
        prev_month_start = date(today.year - 1, 12, 1)
    else:
        prev_month_start = date(today.year, today.month - 1, 1)
        
    if today.month == 12:
        next_month_start = date(today.year + 1, 1, 1)
    else:
        next_month_start = date(today.year, today.month + 1, 1)

    if request.method == 'POST':
        action = request.POST.get('action')
        
        def parse_month(month_str):
            if month_str and len(month_str) == 7: # YYYY-MM
                return month_str + '-01'
            return month_str

        
        if action == 'add_order':
            PlannedOrder.objects.create(
                title=request.POST.get('title'),
                amount=request.POST.get('amount') or 0,
                expected_month=parse_month(request.POST.get('expected_month')),
            )
            messages.success(request, 'Planned order added.')
            
        elif action == 'add_purchase':
            PlannedPurchase.objects.create(
                title=request.POST.get('title'),
                amount=request.POST.get('amount') or 0,
                expected_month=parse_month(request.POST.get('expected_month')),
            )
            messages.success(request, 'Planned purchase added.')
            
        elif action == 'edit_order':
            order = PlannedOrder.objects.get(id=request.POST.get('id'))
            order.title = request.POST.get('title', order.title)
            order.amount = request.POST.get('amount') or order.amount
            if request.POST.get('expected_month'):
                order.expected_month = parse_month(request.POST.get('expected_month'))
            order.payments_received = request.POST.get('payments_received') or 0
            order.status = request.POST.get('status')
            if order.status == 'Completed' and not order.completed_month:
                order.completed_month = current_month_start
            elif order.status != 'Completed':
                order.completed_month = None
            order.save()
            messages.success(request, 'Order updated.')
            
        elif action == 'edit_purchase':
            purchase = PlannedPurchase.objects.get(id=request.POST.get('id'))
            purchase.title = request.POST.get('title', purchase.title)
            purchase.amount = request.POST.get('amount') or purchase.amount
            if request.POST.get('expected_month'):
                purchase.expected_month = parse_month(request.POST.get('expected_month'))
            purchase.payments_given = request.POST.get('payments_given') or 0
            purchase.status = request.POST.get('status')
            if purchase.status == 'Completed' and not purchase.completed_month:
                purchase.completed_month = current_month_start
            elif purchase.status != 'Completed':
                purchase.completed_month = None
            purchase.save()
            messages.success(request, 'Purchase updated.')

        elif action == 'delete_order':
            order = PlannedOrder.objects.get(id=request.POST.get('id'))
            order.delete()
            messages.success(request, 'Order deleted.')

        elif action == 'delete_purchase':
            purchase = PlannedPurchase.objects.get(id=request.POST.get('id'))
            purchase.delete()
            messages.success(request, 'Purchase deleted.')
            
        return redirect('business_planning')

    def get_month_items(model, month_start, is_current=False):
        if is_current:
            return model.objects.filter(
                Q(expected_month=month_start) | 
                (Q(expected_month__lt=month_start) & ~Q(status='Completed'))
            ).order_by('expected_month', '-created_at')
        else:
            if month_start < current_month_start:
                return model.objects.filter(completed_month=month_start).order_by('-created_at')
            else:
                return model.objects.filter(expected_month__gt=current_month_start).order_by('expected_month', '-created_at')

    context = {
        'current_month_start': current_month_start,
        'prev_month_start': prev_month_start,
        'next_month_start': next_month_start,
        
        'curr_orders': get_month_items(PlannedOrder, current_month_start, True),
        'curr_purchases': get_month_items(PlannedPurchase, current_month_start, True),
        
        'prev_orders': get_month_items(PlannedOrder, prev_month_start, False),
        'prev_purchases': get_month_items(PlannedPurchase, prev_month_start, False),
        
        'next_orders': get_month_items(PlannedOrder, next_month_start, False),
        'next_purchases': get_month_items(PlannedPurchase, next_month_start, False),
    }

    # Calculate Totals using Django aggregation
    context['curr_orders_total'] = context['curr_orders'].aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    context['curr_purchases_total'] = context['curr_purchases'].aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    context['prev_orders_total'] = context['prev_orders'].aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    context['prev_purchases_total'] = context['prev_purchases'].aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    context['next_orders_total'] = context['next_orders'].aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    context['next_purchases_total'] = context['next_purchases'].aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    return render(request, 'reporting/planning_dashboard.html', context)
