from core.decorators import require_permission
import json

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
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

        elif action == 'bulk_import_orders':
            titles = request.POST.getlist('import_title')
            amounts = request.POST.getlist('import_amount')
            months = request.POST.getlist('import_month')
            selected_indices = request.POST.getlist('selected_orders')

            created_count = 0
            for idx_str in selected_indices:
                try:
                    idx = int(idx_str)
                    if idx < len(titles) and titles[idx]:
                        PlannedOrder.objects.create(
                            title=titles[idx].strip(),
                            amount=Decimal(amounts[idx] or '0'),
                            expected_month=parse_month(months[idx]) or current_month_start,
                        )
                        created_count += 1
                except (ValueError, IndexError):
                    continue
            messages.success(request, f'{created_count} order(s) successfully imported into execution plan.')

        elif action == 'bulk_import_purchases':
            titles = request.POST.getlist('import_title')
            amounts = request.POST.getlist('import_amount')
            months = request.POST.getlist('import_month')
            selected_indices = request.POST.getlist('selected_purchases')

            created_count = 0
            for idx_str in selected_indices:
                try:
                    idx = int(idx_str)
                    if idx < len(titles) and titles[idx]:
                        PlannedPurchase.objects.create(
                            title=titles[idx].strip(),
                            amount=Decimal(amounts[idx] or '0'),
                            expected_month=parse_month(months[idx]) or current_month_start,
                        )
                        created_count += 1
                except (ValueError, IndexError):
                    continue
            messages.success(request, f'{created_count} purchase(s) successfully imported into execution plan.')
            
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

    # ── Rollover Analytics ──
    rolled_over_orders = PlannedOrder.objects.filter(
        expected_month__lt=current_month_start
    ).exclude(status='Completed')
    rolled_over_orders_count = rolled_over_orders.count()
    rolled_over_orders_total = rolled_over_orders.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

    rolled_over_purchases = PlannedPurchase.objects.filter(
        expected_month__lt=current_month_start
    ).exclude(status='Completed')
    rolled_over_purchases_count = rolled_over_purchases.count()
    rolled_over_purchases_total = rolled_over_purchases.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')

    has_rollover = (rolled_over_orders_count > 0 or rolled_over_purchases_count > 0)

    # ── Cash Gap Analysis ──
    curr_orders_total = context['curr_orders_total']
    curr_purchases_total = context['curr_purchases_total']
    cash_gap = curr_orders_total - curr_purchases_total
    is_cash_deficit = (curr_purchases_total > curr_orders_total) and (curr_purchases_total > 0)
    cash_deficit_amount = (curr_purchases_total - curr_orders_total) if is_cash_deficit else Decimal('0.00')
    cash_surplus_amount = (curr_orders_total - curr_purchases_total) if not is_cash_deficit else Decimal('0.00')

    profit_margin_pct = Decimal('0.0')
    if curr_orders_total > 0:
        profit_margin_pct = round(((curr_orders_total - curr_purchases_total) / curr_orders_total) * 100, 1)

    # ── Auto-Import Candidates from ERP ──
    existing_order_titles = set(PlannedOrder.objects.values_list('title', flat=True))
    available_orders = []

    try:
        from tracker.models import Order as TrackerOrder
        tracker_orders = TrackerOrder.objects.filter(
            order_status__in=['OPEN', 'SOURCING', 'PROCURED']
        ).prefetch_related('products').order_by('-order_date')[:30]

        for to in tracker_orders:
            sp_total = sum((p.selling_price_inc_gst or 0) * (p.quantity or 1) for p in to.products.all())
            title = f"Tracker #{to.order_number}: {to.customer_name}"
            if title not in existing_order_titles:
                available_orders.append({
                    'source': 'Tracker Order',
                    'badge_color': 'indigo',
                    'title': title,
                    'amount': float(sp_total),
                    'ref': to.order_number,
                })
    except Exception:
        tracker_orders = []

    try:
        doc_orders = Document.objects.filter(
            type__in=['PRO', 'QTN'],
            status='Approved'
        ).select_related('contact').order_by('-date')[:30]

        for doc in doc_orders:
            c_name = doc.contact.name if doc.contact else (doc.customer_name or 'Client')
            title = f"{doc.get_type_display()} {doc.number}: {c_name}"
            if title not in existing_order_titles:
                available_orders.append({
                    'source': doc.get_type_display(),
                    'badge_color': 'emerald',
                    'title': title,
                    'amount': float(doc.balance_due or doc.grand_total or 0),
                    'ref': doc.number,
                })
    except Exception:
        pass

    # Available Purchases from ERP
    existing_purchase_titles = set(PlannedPurchase.objects.values_list('title', flat=True))
    available_purchases = []

    try:
        pos = Document.objects.filter(
            type='PO'
        ).exclude(status='Cancelled').select_related('contact').order_by('-date')[:30]

        for po in pos:
            v_name = po.contact.name if po.contact else (po.vendor_name or 'Supplier')
            title = f"PO {po.number}: {v_name}"
            if title not in existing_purchase_titles:
                available_purchases.append({
                    'source': 'Purchase Order',
                    'badge_color': 'purple',
                    'title': title,
                    'amount': float(po.balance_due or po.grand_total or 0),
                    'ref': po.number,
                })
    except Exception:
        pass

    try:
        for to in tracker_orders:
            bp_total = sum((p.buying_price_inc_gst or 0) * (p.quantity or 1) for p in to.products.all() if p.buying_price_inc_gst)
            if bp_total > 0:
                title = f"Tracker Procure #{to.order_number}: {to.customer_name}"
                if title not in existing_purchase_titles:
                    available_purchases.append({
                        'source': 'Tracker Procurement',
                        'badge_color': 'violet',
                        'title': title,
                        'amount': float(bp_total),
                        'ref': to.order_number,
                    })
    except Exception:
        pass

    # Autocomplete Contacts
    try:
        from contacts.models import Contact
        customer_names = list(Contact.objects.filter(contact_type__in=['Customer', 'Both']).values_list('name', flat=True).distinct()[:100])
        vendor_names = list(Contact.objects.filter(contact_type__in=['Vendor', 'Both']).values_list('name', flat=True).distinct()[:100])
    except Exception:
        customer_names, vendor_names = [], []

    context.update({
        'rolled_over_orders_count': rolled_over_orders_count,
        'rolled_over_orders_total': rolled_over_orders_total,
        'rolled_over_purchases_count': rolled_over_purchases_count,
        'rolled_over_purchases_total': rolled_over_purchases_total,
        'has_rollover': has_rollover,
        'is_cash_deficit': is_cash_deficit,
        'cash_deficit_amount': cash_deficit_amount,
        'cash_surplus_amount': cash_surplus_amount,
        'profit_margin_pct': profit_margin_pct,
        'cash_gap': cash_gap,
        'available_orders': available_orders,
        'available_purchases': available_purchases,
        'customer_names': customer_names,
        'vendor_names': vendor_names,
    })

    return render(request, 'reporting/planning_dashboard.html', context)


# ─── Live P&L Statement ────────────────────────────────────────────────────────

def _get_pl_date_range(request):
    """Parse period/custom date range from request for P&L views."""
    today = date.today()
    period = request.GET.get('period', 'this_fy')

    ranges = {
        'today': (today, today, 'Today'),
        'this_week': (today - timedelta(days=today.weekday()), today, 'This Week'),
        'this_month': (today.replace(day=1), today, f"{today.strftime('%B %Y')}"),
        'last_month': None,  # computed below
        'this_quarter': None,
        'this_fy': None,
        'last_fy': None,
    }

    if period == 'last_month':
        first_of_this = today.replace(day=1)
        end = first_of_this - timedelta(days=1)
        start = end.replace(day=1)
        label = end.strftime('%B %Y')
        return period, start, end, label

    if period == 'this_quarter':
        q = (today.month - 1) // 3
        start = date(today.year, q * 3 + 1, 1)
        label = f"Q{q+1} {today.year}"
        return period, start, today, label

    if period == 'this_fy':
        fy_y = today.year if today.month >= 4 else today.year - 1
        start = date(fy_y, 4, 1)
        label = f"FY {fy_y}–{str(fy_y + 1)[2:]}"
        return period, start, today, label

    if period == 'last_fy':
        fy_y = (today.year if today.month >= 4 else today.year - 1) - 1
        start = date(fy_y, 4, 1)
        end = date(fy_y + 1, 3, 31)
        label = f"FY {fy_y}–{str(fy_y + 1)[2:]}"
        return period, start, end, label

    if period == 'custom':
        try:
            start = date.fromisoformat(request.GET.get('start', ''))
            end = date.fromisoformat(request.GET.get('end', ''))
            label = f"{start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}"
            return period, start, end, label
        except (ValueError, TypeError):
            pass

    # default: this_fy
    fy_y = today.year if today.month >= 4 else today.year - 1
    start = date(fy_y, 4, 1)
    label = f"FY {fy_y}–{str(fy_y + 1)[2:]}"
    return 'this_fy', start, today, label


def _compute_pl(start_date, end_date):
    """Return a dict of all P&L line items for the given date range."""
    from decimal import Decimal
    from django.db.models import Sum, Count, Q
    from documents.models import Document
    from payments.models import Payment, Expense

    Z = Decimal('0')

    # ── Revenue (Invoices approved in period) ────────────────────────────────
    inv_qs = Document.objects.filter(type='INV', status='Approved',
                                     date__gte=start_date, date__lte=end_date)
    revenue_gross = inv_qs.aggregate(t=Sum('grand_total'))['t'] or Z
    revenue_subtotal = inv_qs.aggregate(t=Sum('subtotal'))['t'] or Z
    revenue_tax = inv_qs.aggregate(t=Sum('tax_total'))['t'] or Z
    invoice_count = inv_qs.count()

    # Credit / Debit Note adjustments
    crn = Document.objects.filter(type='CRN', status='Approved',
                                  date__gte=start_date, date__lte=end_date
                                  ).aggregate(t=Sum('grand_total'))['t'] or Z
    dbn = Document.objects.filter(type='DBN', status='Approved',
                                  date__gte=start_date, date__lte=end_date
                                  ).aggregate(t=Sum('grand_total'))['t'] or Z
    net_revenue = revenue_gross - crn + dbn

    # Proforma Invoices
    pi_qs = Document.objects.filter(type='PRO', status='Approved',
                                    date__gte=start_date, date__lte=end_date)
    pi_amount = pi_qs.aggregate(t=Sum('grand_total'))['t'] or Z

    # Quotations
    qtn_qs = Document.objects.filter(type='QTN', status='Approved',
                                     date__gte=start_date, date__lte=end_date)
    qtn_amount = qtn_qs.aggregate(t=Sum('grand_total'))['t'] or Z

    # ── COGS: Purchase Orders approved in period ─────────────────────────────
    cogs = Document.objects.filter(type='PO', status='Approved',
                                   date__gte=start_date, date__lte=end_date
                                   ).aggregate(t=Sum('grand_total'))['t'] or Z

    # EDMS vendor invoices
    edms_purchases = Z
    try:
        from edms.models import EDMSDocumentCategory, EDMSDocument
        inv_cat = EDMSDocumentCategory.objects.filter(name__icontains='invoice', is_active=True).first()
        if inv_cat:
            edms_purchases = EDMSDocument.objects.filter(
                is_deleted=False, category=inv_cat,
                invoice_date__gte=start_date, invoice_date__lte=end_date
            ).aggregate(t=Sum('amount'))['t'] or Z
    except Exception:
        pass
    total_cogs = cogs + edms_purchases

    gross_profit = net_revenue - total_cogs
    gross_margin = (gross_profit / net_revenue * 100) if net_revenue else Z

    # ── Operating Expenses ───────────────────────────────────────────────────
    exp_qs = Expense.objects.filter(date__gte=start_date, date__lte=end_date, status='Approved')
    total_opex = exp_qs.aggregate(t=Sum('amount'))['t'] or Z

    DAILY_TYPES = ['Petrol and Diesel', 'Travel', 'Hotel', 'Food Expenses',
                   'Office stationary', 'Courier expenses', 'Transportation Payment',
                   'Marketing Expenses', 'Customer Delight', 'Other Daily']
    FIXED_TYPES = ['Staff salary', 'OFC rent', 'Electricity bill', 'Internet Bill',
                   'Google workspace', 'Website and hosting cost', 'Other Fixed']
    daily_opex = exp_qs.filter(expense_type__in=DAILY_TYPES).aggregate(t=Sum('amount'))['t'] or Z
    fixed_opex = exp_qs.filter(expense_type__in=FIXED_TYPES).aggregate(t=Sum('amount'))['t'] or Z

    expense_breakdown = list(
        exp_qs.values('expense_type')
        .annotate(total=Sum('amount'), count=Count('id'))
        .order_by('-total')[:10]
    )

    # ── Net Profit ───────────────────────────────────────────────────────────
    net_profit = gross_profit - total_opex
    net_margin = (net_profit / net_revenue * 100) if net_revenue else Z

    # ── Cash Position ───────────────────────────────────────────────────────
    payments_in = Payment.objects.filter(
        date__gte=start_date, date__lte=end_date
    ).aggregate(t=Sum('amount'))['t'] or Z
    outstanding_receivables = max(Z, net_revenue - payments_in)

    # ── Monthly trend (last 12 months) ──────────────────────────────────────
    today = date.today()
    monthly_trend = []
    for i in range(11, -1, -1):
        ref = today.replace(day=1)
        # go back i months
        m = ref.month - i
        y = ref.year
        while m <= 0:
            m += 12
            y -= 1
        ms = date(y, m, 1)
        me = date(y, m + 1, 1) - timedelta(days=1) if m < 12 else date(y, 12, 31)

        m_rev = Document.objects.filter(type='INV', status='Approved',
                                        date__gte=ms, date__lte=me
                                        ).aggregate(t=Sum('grand_total'))['t'] or Z
        m_cogs = Document.objects.filter(type='PO', status='Approved',
                                         date__gte=ms, date__lte=me
                                         ).aggregate(t=Sum('grand_total'))['t'] or Z
        m_exp = Expense.objects.filter(status='Approved', date__gte=ms, date__lte=me
                                       ).aggregate(t=Sum('amount'))['t'] or Z
        monthly_trend.append({
            'month': ms.strftime('%b %Y'),
            'revenue': float(m_rev),
            'cogs': float(m_cogs),
            'opex': float(m_exp),
            'profit': float(m_rev - m_cogs - m_exp),
        })

    return {
        'revenue_gross': revenue_gross,
        'revenue_subtotal': revenue_subtotal,
        'revenue_tax': revenue_tax,
        'net_revenue': net_revenue,
        'invoice_count': invoice_count,
        'pi_amount': pi_amount,
        'qtn_amount': qtn_amount,
        'crn': crn,
        'dbn': dbn,
        'cogs': cogs,
        'edms_purchases': edms_purchases,
        'total_cogs': total_cogs,
        'gross_profit': gross_profit,
        'gross_margin': gross_margin,
        'total_opex': total_opex,
        'daily_opex': daily_opex,
        'fixed_opex': fixed_opex,
        'expense_breakdown': expense_breakdown,
        'net_profit': net_profit,
        'net_margin': net_margin,
        'payments_in': payments_in,
        'outstanding_receivables': outstanding_receivables,
        'monthly_trend': monthly_trend,
    }


@require_permission('REPORTING', 'read')
def profit_and_loss_view(request):
    """Dedicated Live Profit & Loss Statement page."""
    period, start_date, end_date, label = _get_pl_date_range(request)
    pl = _compute_pl(start_date, end_date)

    periods = [
        ('today', 'Today'),
        ('this_week', 'This Week'),
        ('this_month', 'This Month'),
        ('last_month', 'Last Month'),
        ('this_quarter', 'This Quarter'),
        ('this_fy', 'This FY'),
        ('last_fy', 'Last FY'),
        ('custom', 'Custom Range'),
    ]

    context = {
        'period': period,
        'periods': periods,
        'label': label,
        'start_date': start_date,
        'end_date': end_date,
        'monthly_trend_json': json.dumps(pl['monthly_trend']),
        **pl,
    }
    return render(request, 'reporting/profit_and_loss.html', context)


@require_permission('REPORTING', 'read')
def profit_and_loss_api(request):
    """JSON API returning P&L numbers for a given period — used by Chart.js."""
    from django.http import JsonResponse
    from decimal import Decimal

    period, start_date, end_date, label = _get_pl_date_range(request)
    pl = _compute_pl(start_date, end_date)

    def dec2f(v):
        return float(v) if isinstance(v, Decimal) else v

    return JsonResponse({
        'label': label,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'net_revenue': dec2f(pl['net_revenue']),
        'total_cogs': dec2f(pl['total_cogs']),
        'gross_profit': dec2f(pl['gross_profit']),
        'gross_margin': dec2f(pl['gross_margin']),
        'total_opex': dec2f(pl['total_opex']),
        'net_profit': dec2f(pl['net_profit']),
        'net_margin': dec2f(pl['net_margin']),
        'monthly_trend': pl['monthly_trend'],
    })


# ─── Other Office Tools: Customer Statement of Account Ledger ────────────────

def _build_contact_statement_ledger(contact, start_date=None, end_date=None):
    """
    Computes a clean chronological debit/credit running balance statement.
    Invoices & Unlinked Proforma Invoices = Debit (+), Payments = Credit (-).
    """
    from contacts.models import Contact
    from documents.models import Document
    from payments.models import Payment
    from config.models import CompanyProfile

    company = CompanyProfile.objects.first()

    # Base querysets
    invoices = Document.objects.filter(contact=contact, type='INV').exclude(status='Cancelled')
    
    # Proforma Invoices: only include PIs that are NOT linked to any Tax Invoice
    all_pis = Document.objects.filter(contact=contact, type='PRO').exclude(status='Cancelled')
    unlinked_pi_ids = [pi.id for pi in all_pis if not pi.has_linked_invoice]
    unlinked_pis = Document.objects.filter(id__in=unlinked_pi_ids)
    
    payments = Payment.objects.filter(contact=contact)

    # Opening balance before start_date
    opening_balance = Decimal('0.00')
    if start_date:
        prior_inv_debits = invoices.filter(date__lt=start_date).aggregate(total=Sum('grand_total'))['total'] or Decimal('0.00')
        prior_pi_debits = unlinked_pis.filter(date__lt=start_date).aggregate(total=Sum('grand_total'))['total'] or Decimal('0.00')
        prior_credits = payments.filter(date__lt=start_date).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        opening_balance = (prior_inv_debits + prior_pi_debits) - prior_credits

        invoices = invoices.filter(date__gte=start_date)
        unlinked_pis = unlinked_pis.filter(date__gte=start_date)
        payments = payments.filter(date__gte=start_date)

    if end_date:
        invoices = invoices.filter(date__lte=end_date)
        unlinked_pis = unlinked_pis.filter(date__lte=end_date)
        payments = payments.filter(date__lte=end_date)

    # Build chronological entries
    entries = []

    for inv in invoices:
        entries.append({
            'date': inv.date or inv.created_at.date(),
            'type': 'INVOICE',
            'type_display': 'Tax Invoice',
            'doc_number': inv.number,
            'ref_no': inv.po_reference_number or '—',
            'details': f"Tax Invoice #{inv.number}",
            'debit': Decimal(str(inv.grand_total or 0)),
            'credit': Decimal('0.00'),
            'doc_id': inv.id,
        })

    for pi in unlinked_pis:
        entries.append({
            'date': pi.date or pi.created_at.date(),
            'type': 'PROFORMA',
            'type_display': 'Proforma Invoice',
            'doc_number': pi.number,
            'ref_no': pi.po_reference_number or '—',
            'details': f"Proforma Invoice #{pi.number}",
            'debit': Decimal(str(pi.grand_total or 0)),
            'credit': Decimal('0.00'),
            'doc_id': pi.id,
        })

    for pay in payments:
        entries.append({
            'date': pay.date,
            'type': 'PAYMENT',
            'type_display': f"Payment ({pay.payment_mode})",
            'doc_number': pay.document_ref or '—',
            'ref_no': pay.reference_number or '—',
            'details': f"Received via {pay.payment_mode}" + (f" ({pay.notes})" if pay.notes else ""),
            'debit': Decimal('0.00'),
            'credit': Decimal(str(pay.amount or 0)),
            'doc_id': None,
        })

    # Sort chronologically by date
    entries.sort(key=lambda x: x['date'])

    # Compute running balance
    running_balance = opening_balance
    total_debit = Decimal('0.00')
    total_credit = Decimal('0.00')

    for item in entries:
        running_balance += (item['debit'] - item['credit'])
        item['balance'] = running_balance
        total_debit += item['debit']
        total_credit += item['credit']

    closing_balance = running_balance


    return {
        'contact': contact,
        'company': company,
        'opening_balance': opening_balance,
        'entries': entries,
        'total_debit': total_debit,
        'total_credit': total_credit,
        'closing_balance': closing_balance,
        'start_date': start_date,
        'end_date': end_date,
    }


@require_permission('REPORTING', 'read')
def statement_of_account_view(request):
    """
    Office Tool: Interactive Customer Statement of Account Ledger.
    Allows staff to select any customer, choose date range, see running balance,
    and generate secure WhatsApp / Email links or printable PDFs.
    """
    from contacts.models import Contact
    from django.core.signing import Signer

    contacts = Contact.objects.filter(contact_type__in=['Customer', 'Both']).order_by('name')

    selected_contact_id = request.GET.get('contact_id')
    start_date_str = request.GET.get('start_date', '').strip()
    end_date_str = request.GET.get('end_date', '').strip()

    selected_contact = None
    ledger_data = None
    public_token = None
    public_url = None

    if selected_contact_id:
        try:
            selected_contact = Contact.objects.get(id=selected_contact_id)
            start_date = date.fromisoformat(start_date_str) if start_date_str else None
            end_date = date.fromisoformat(end_date_str) if end_date_str else None

            ledger_data = _build_contact_statement_ledger(selected_contact, start_date, end_date)

            # Generate secure URL-safe token for customer sharing
            from django.core import signing
            payload = {
                'c': selected_contact.id,
                's': start_date_str,
                'e': end_date_str,
            }
            public_token = signing.dumps(payload, salt="statement-public-salt")
            site_url = request.build_absolute_uri('/')[:-1]
            public_url = f"{site_url}/reports/statement/v/{public_token}/"
        except Exception:
            pass

    return render(request, 'reporting/statement_of_account.html', {
        'contacts': contacts,
        'selected_contact': selected_contact,
        'ledger': ledger_data,
        'public_token': public_token,
        'public_url': public_url,
        'start_date': start_date_str,
        'end_date': end_date_str,
    })


def public_statement_view(request, token):
    """
    Publicly view/download a Statement of Account securely using a cryptographically signed token.
    Customers CANNOT change the URL ID to view other clients' ledgers.
    No login required for the customer.
    """
    from contacts.models import Contact
    from django.core import signing
    try:
        data = signing.loads(token, salt="statement-public-salt")
        contact_id = data.get('c')
        start_date_str = data.get('s', '')
        end_date_str = data.get('e', '')
        start_date = date.fromisoformat(start_date_str) if start_date_str else None
        end_date = date.fromisoformat(end_date_str) if end_date_str else None
    except (signing.BadSignature, Exception):
        return HttpResponse("<h1>403 Forbidden</h1><p>Invalid or expired statement link.</p>", status=403)

    contact = get_object_or_404(Contact, id=contact_id)
    ledger_data = _build_contact_statement_ledger(contact, start_date, end_date)

    return render(request, 'reporting/public_statement_view.html', {
        'contact': contact,
        'ledger': ledger_data,
        'token': token,
    })


@require_permission('REPORTING', 'read')
def daily_digest_view(request):
    """
    Day-End Business Digest — Daily summary of invoices generated, payments collected,
    goods dispatched (Delivery Challans), quotations issued, and current outstanding receivables.
    """
    target_date_str = request.GET.get('date', '').strip()
    if target_date_str:
        try:
            target_date = date.fromisoformat(target_date_str)
        except ValueError:
            target_date = timezone.localdate()
    else:
        target_date = timezone.localdate()

    # Previous and Next day for quick navigation
    prev_date = target_date - timedelta(days=1)
    next_date = target_date + timedelta(days=1)
    is_today = (target_date == timezone.localdate())

    # 1. Documents generated on target_date
    day_docs = Document.objects.filter(date=target_date).select_related('contact').order_by('-id')
    invoices = day_docs.filter(type__in=['INV', 'PRO'])
    challans = day_docs.filter(type='CHL')
    quotes = day_docs.filter(type='QTN')
    pos = day_docs.filter(type='PO')

    total_billed = invoices.aggregate(total=Coalesce(Sum('grand_total'), Value(0, output_field=DecimalField())))['total']
    total_quotes_val = quotes.aggregate(total=Coalesce(Sum('grand_total'), Value(0, output_field=DecimalField())))['total']

    # 2. Payments collected on target_date
    day_payments = Payment.objects.filter(date=target_date).select_related('contact').order_by('-id')
    total_collected = day_payments.aggregate(total=Coalesce(Sum('amount'), Value(0, output_field=DecimalField())))['total']

    # Breakdown by payment mode
    payment_modes = day_payments.values('payment_mode').annotate(total=Sum('amount'), count=Count('id')).order_by('-total')

    # 3. Key business metrics summary
    from contacts.models import Contact
    # Top 5 Outstanding Customer Balances
    customers = Contact.objects.filter(contact_type__in=['Customer', 'Both']).annotate(
        total_inv=Coalesce(Sum('documents__grand_total', filter=Q(documents__type__in=['INV', 'PRO'])), Value(0, output_field=DecimalField())),
        total_paid=Coalesce(Sum('payments__amount'), Value(0, output_field=DecimalField()))
    )
    overdue_customers = []
    total_receivable = Decimal('0.00')
    for c in customers:
        due = c.total_inv - c.total_paid
        if due > 0:
            total_receivable += due
            overdue_customers.append({
                'id': c.id,
                'name': c.name,
                'phone': c.phone,
                'due': due
            })
    overdue_customers.sort(key=lambda x: x['due'], reverse=True)
    top_receivables = overdue_customers[:5]

    return render(request, 'reporting/daily_digest.html', {
        'target_date': target_date,
        'prev_date': prev_date,
        'next_date': next_date,
        'is_today': is_today,
        'invoices': invoices,
        'challans': challans,
        'quotes': quotes,
        'pos': pos,
        'payments': day_payments,
        'payment_modes': payment_modes,
        'total_billed': total_billed,
        'total_quotes_val': total_quotes_val,
        'total_collected': total_collected,
        'total_receivable': total_receivable,
        'top_receivables': top_receivables,
    })
